import logging

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import OneTimePassword, OtpPurpose, UserRole
from accounts.serializers import (
    OtpVerificationSerializer,
    ErrorResponseSerializer,
    ForgotPasswordRequestOtpSerializer,
    ForgotPasswordResetSerializer,
    ForgotPasswordVerifyOtpSerializer,
    ResendOtpSerializer,
    SignInSerializer,
    SignInSuccessResponseSerializer,
    SignUpSerializer,
    SignUpSuccessResponseSerializer,
    SuccessMessageResponseSerializer,
    TokenRefreshRequestSerializer,
    TokenRefreshSuccessResponseSerializer,
    UserSerializer,
    MeSuccessResponseSerializer,
    OtpVerifiedSuccessResponseSerializer,
    PushTokenUpdateSerializer,
    TogglePushNotificationSerializer,
    AccountDeleteSerializer,
    ChangePasswordSerializer,
)
from accounts.utils import issue_and_send_otp
from common.responses import created_response, error_response, success_response
from common.throttles import (
    OTP_SEND_THROTTLES,
    OTP_VERIFY_THROTTLES,
    SignInThrottle,
    SignUpThrottle,
    TestPushThrottle,
)
from common.push import send_test_push
from common.utils import send_expo_push_notification

User = get_user_model()
logger = logging.getLogger(__name__)

INVALID_OTP_MESSAGE = "Invalid or expired OTP."
OTP_SENT_GENERIC_MESSAGE = "If an account exists for this email, an OTP has been sent."


def _get_user_by_email(email):
    return User.objects.filter(email=email.lower()).first()


def _forgot_password_verified_cache_key(email):
    return f"accounts:forgot-password:verified:{email.lower()}"


def _build_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def _get_valid_otp(user, purpose, code):
    # Attempt-limited: 5 wrong guesses burns the OTP (see OneTimePassword.verify).
    return OneTimePassword.verify(user, purpose, code)


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_sign_up",
    request=SignUpSerializer,
    responses={
        201: SignUpSuccessResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Validation error."),
        409: OpenApiResponse(response=ErrorResponseSerializer, description="Email already exists."),
        500: OpenApiResponse(response=ErrorResponseSerializer, description="OTP email sending failed."),
    },
    description="Create a student account using full name, email, and password. A 4 digit OTP is sent by email for verification.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([SignUpThrottle, *OTP_SEND_THROTTLES])
def sign_up(request):
    serializer = SignUpSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    validated_data = serializer.validated_data
    email = validated_data["email"]

    with transaction.atomic():
        user = _get_user_by_email(email)
        if user and user.is_email_verified:
            return error_response("An account with this email already exists.", status_code=status.HTTP_409_CONFLICT)

        if user is None:
            user = User.objects.create_user(
                email=email,
                full_name=validated_data["full_name"],
                password=validated_data["password"],
                role=UserRole.STUDENT,
                is_active=False,
                is_email_verified=False,
            )
        else:
            user.full_name = validated_data["full_name"]
            user.role = UserRole.STUDENT
            user.is_active = False
            user.is_email_verified = False
            user.set_password(validated_data["password"])
            user.save(
                update_fields=["full_name", "role", "is_active", "is_email_verified", "password", "updated_at"]
            )

    try:
        issue_and_send_otp(user, OtpPurpose.SIGNUP)
    except Exception:
        logger.exception("Failed to send OTP email to user %s", user.pk)
        return error_response("Failed to send OTP email.", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return created_response(
        {
            "user": UserSerializer(user, context={"request": request}).data,
            "next_step": "Verify the 4 digit OTP sent to your email to activate your account.",
        },
        message="Student account created. OTP sent to email.",
    )


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_verify_sign_up_otp",
    request=OtpVerificationSerializer,
    responses={
        200: OtpVerifiedSuccessResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="OTP is invalid or expired."),
    },
    description="Verify the sign-up OTP and receive JWT access and refresh tokens.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes(OTP_VERIFY_THROTTLES)
def verify_sign_up_otp(request):
    serializer = OtpVerificationSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = _get_user_by_email(serializer.validated_data["email"])
    otp = _get_valid_otp(user, OtpPurpose.SIGNUP, serializer.validated_data["otp"]) if user else None
    if otp is None:
        return error_response(INVALID_OTP_MESSAGE, status_code=status.HTTP_400_BAD_REQUEST)

    user.is_active = True
    user.is_email_verified = True
    user.save(update_fields=["is_active", "is_email_verified", "updated_at"])

    return success_response(
        {
            "user": UserSerializer(user, context={"request": request}).data,
            "tokens": _build_tokens_for_user(user),
            "is_profile_completed": user.is_profile_completed,
        },
        message="Account verified successfully.",
    )


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_sign_in",
    request=SignInSerializer,
    responses={
        200: SignInSuccessResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid credentials or validation error."),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="Account is not verified yet."),
    },
    description="Sign in a verified user with email and password and return JWT access and refresh tokens.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([SignInThrottle])
def sign_in(request):
    serializer = SignInSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]
    user = _get_user_by_email(email)

    if user is None or not user.check_password(password):
        return error_response("Invalid email or password.", status_code=status.HTTP_400_BAD_REQUEST)

    if not user.is_active or not user.is_email_verified:
        return error_response(
            "Account is not verified yet. Please verify your email OTP first.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Recompute is_profile_completed from DB on every login
    if user.role == "student":
        from students.views import _compute_profile_completion
        is_completed = _compute_profile_completion(user)
        if user.is_profile_completed != is_completed:
            user.is_profile_completed = is_completed
            user.save(update_fields=["is_profile_completed", "updated_at"])

    # Send push notification (silent fail — won't break login if it fails)
    if user.expo_push_token and user.is_push_notification:
        send_expo_push_notification(
            push_tokens=user.expo_push_token,
            title="Login Successful 🎉",
            body="Welcome back! You have logged in successfully.",
        )

    return success_response(
        {
            "user": UserSerializer(user, context={"request": request}).data,
            "tokens": _build_tokens_for_user(user),
            "is_profile_completed": user.is_profile_completed,
        },
        message="Sign in completed successfully.",
    )


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_resend_otp",
    request=ResendOtpSerializer,
    responses={
        200: SuccessMessageResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="OTP resend is not allowed for the current user state."),
        500: OpenApiResponse(response=ErrorResponseSerializer, description="OTP email sending failed."),
    },
    description="Resend a 4 digit OTP for sign-up verification.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes(OTP_SEND_THROTTLES)
def resend_otp(request):
    serializer = ResendOtpSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = _get_user_by_email(serializer.validated_data["email"])
    if user is None:
        return success_response(message=OTP_SENT_GENERIC_MESSAGE)

    purpose = serializer.validated_data["purpose"]
    if purpose == OtpPurpose.SIGNUP and user.is_email_verified:
        return error_response("This account is already verified.", status_code=status.HTTP_400_BAD_REQUEST)

    try:
        issue_and_send_otp(user, purpose)
    except Exception:
        logger.exception("Failed to send OTP email to user %s", user.pk)
        return error_response("Failed to send OTP email.", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return success_response(message="OTP sent successfully.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_refresh_token",
    request=TokenRefreshRequestSerializer,
    responses={
        200: TokenRefreshSuccessResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Refresh token is invalid."),
    },
    description="Exchange a valid refresh token for a new access token.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_token(request):
    serializer = TokenRefreshRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    token_serializer = TokenRefreshSerializer(data=serializer.validated_data)
    if not token_serializer.is_valid():
        return error_response("Invalid refresh token.", token_serializer.errors, status.HTTP_400_BAD_REQUEST)

    return success_response(token_serializer.validated_data, message="Token refreshed successfully.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_me",
    responses={
        200: MeSuccessResponseSerializer,
        401: OpenApiResponse(response=ErrorResponseSerializer, description="Authentication credentials were not provided or are invalid."),
    },
    description="Return the currently authenticated user's profile.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return success_response(UserSerializer(request.user, context={"request": request}).data, message="User profile fetched successfully.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_forgot_password_request_otp",
    request=ForgotPasswordRequestOtpSerializer,
    responses={
        200: SuccessMessageResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Validation error."),
        500: OpenApiResponse(response=ErrorResponseSerializer, description="OTP email sending failed."),
    },
    description="Send a 4 digit OTP to the user's email for forgot-password flow.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes(OTP_SEND_THROTTLES)
def forgot_password_request_otp(request):
    serializer = ForgotPasswordRequestOtpSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = _get_user_by_email(serializer.validated_data["email"])
    if user is None:
        return success_response(message=OTP_SENT_GENERIC_MESSAGE)

    cache.delete(_forgot_password_verified_cache_key(user.email))

    try:
        issue_and_send_otp(user, OtpPurpose.FORGOT_PASSWORD)
    except Exception:
        logger.exception("Failed to send OTP email to user %s", user.pk)
        return error_response("Failed to send OTP email.", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return success_response(message="OTP sent successfully.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_forgot_password_verify_otp",
    request=ForgotPasswordVerifyOtpSerializer,
    responses={
        200: SuccessMessageResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Validation error or OTP invalid/expired."),
    },
    description="Verify forgot-password OTP before setting a new password.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes(OTP_VERIFY_THROTTLES)
def forgot_password_verify_otp(request):
    serializer = ForgotPasswordVerifyOtpSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = _get_user_by_email(serializer.validated_data["email"])
    otp = _get_valid_otp(user, OtpPurpose.FORGOT_PASSWORD, serializer.validated_data["otp"]) if user else None
    if otp is None:
        return error_response(INVALID_OTP_MESSAGE, status_code=status.HTTP_400_BAD_REQUEST)

    cache.set(_forgot_password_verified_cache_key(user.email), True, timeout=600)

    return success_response(message="OTP verified successfully.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_forgot_password_reset",
    request=ForgotPasswordResetSerializer,
    responses={
        200: SuccessMessageResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Validation error or OTP invalid/expired."),
    },
    description="Set a new password using email and matching confirm password after OTP has already been verified.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes(OTP_VERIFY_THROTTLES)
def forgot_password_reset(request):
    serializer = ForgotPasswordResetSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = _get_user_by_email(serializer.validated_data["email"])
    if user is None or not cache.get(_forgot_password_verified_cache_key(user.email)):
        return error_response(
            "OTP verification required before resetting password.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        cache.delete(_forgot_password_verified_cache_key(user.email))

    return success_response(message="Password reset successfully.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_update_push_token",
    request=PushTokenUpdateSerializer,
    responses={
        200: SuccessMessageResponseSerializer,
        401: OpenApiResponse(response=ErrorResponseSerializer, description="Unauthenticated."),
    },
    description="Update the user's Expo push token.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_push_token(request):
    serializer = PushTokenUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = request.user
    token = serializer.validated_data["expo_push_token"].strip() or None
    with transaction.atomic():
        if token:
            # A device token belongs to one account at a time; otherwise the
            # previous user on a shared phone keeps receiving notifications.
            User.objects.filter(expo_push_token=token).exclude(pk=user.pk).update(expo_push_token=None)
        user.expo_push_token = token
        user.save(update_fields=["expo_push_token", "updated_at"])

    return success_response(message="Push token updated successfully." if token else "Push token cleared.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_test_push",
    request=None,
    responses={
        200: OpenApiResponse(description="Test notification delivered (or accepted and still pending)."),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="No token saved, or Expo/FCM rejected it."),
        401: OpenApiResponse(response=ErrorResponseSerializer, description="Unauthenticated."),
    },
    description="Send a test push notification to the logged-in user's saved Expo token and report where it failed.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([TestPushThrottle])
def test_push(request):
    result = send_test_push(request.user.expo_push_token, wait_seconds=4)
    data = {
        "stage": result["stage"],
        "hint": result["hint"],
        "ticket": result["ticket"],
        "receipt": result["receipt"],
        "push_enabled": request.user.is_push_notification,
    }
    if result["ok"]:
        return success_response(data, message="Test notification sent.")
    return error_response("Test notification failed.", data, status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_change_password",
    request=ChangePasswordSerializer,
    responses={
        200: SuccessMessageResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Validation error or wrong current password."),
        401: OpenApiResponse(response=ErrorResponseSerializer, description="Unauthenticated."),
    },
    description="Change the logged-in user's password (students and teachers). Requires the current password.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([SignInThrottle])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = request.user
    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password", "updated_at"])
    return success_response(message="Password changed successfully.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_toggle_push_notification",
    request=TogglePushNotificationSerializer,
    responses={
        200: SuccessMessageResponseSerializer,
        401: OpenApiResponse(response=ErrorResponseSerializer, description="Unauthenticated."),
    },
    description="Enable or disable push notifications for the student.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_push_notification(request):
    serializer = TogglePushNotificationSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = request.user
    user.is_push_notification = serializer.validated_data["is_push_notification"]
    user.save(update_fields=["is_push_notification", "updated_at"])

    status_str = "enabled" if user.is_push_notification else "disabled"
    return success_response(message=f"Push notifications {status_str} successfully.")


@extend_schema(
    tags=["Accounts Authentication"],
    operation_id="accounts_delete_account",
    request=AccountDeleteSerializer,
    responses={
        200: SuccessMessageResponseSerializer,
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid password."),
        401: OpenApiResponse(response=ErrorResponseSerializer, description="Unauthenticated."),
    },
    description="Delete the user's account after password verification.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def delete_account(request):
    serializer = AccountDeleteSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    user = request.user
    password = serializer.validated_data["password"]

    if not user.check_password(password):
        return error_response("Invalid password. Account deletion failed.", status_code=status.HTTP_400_BAD_REQUEST)

    user.delete()
    return success_response(message="Account deleted successfully.")
