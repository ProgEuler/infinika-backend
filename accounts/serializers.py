from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from accounts.models import OtpPurpose

User = get_user_model()


def _get_student_location_model():
    """Lazy import to avoid circular imports."""
    from students.models import StudentLocation
    return StudentLocation


class UserSerializer(serializers.ModelSerializer):
    is_location = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()
    level_id = serializers.SerializerMethodField()
    student_id = serializers.SerializerMethodField()
    attempt_id = serializers.SerializerMethodField()

    def get_is_location(self, obj):
        if obj.role == "student":
            StudentLocation = _get_student_location_model()
            return StudentLocation.objects.filter(student=obj).exists()
        elif obj.role == "teacher":
            try:
                from teachers.models import TeachersLocation
                has_geo = TeachersLocation.objects.filter(teacher__user=obj).exists()
                if has_geo:
                    return True
                # Fallback to checking offline_location in profile
                profile = getattr(obj, "teacher_profile", None)
                return bool(profile and profile.offline_location)
            except Exception:
                return False
        return False

    def get_student_id(self, obj):
        if obj.role == "student":
            try:
                return obj.student_profile.id
            except Exception:
                pass
        return None

    def get_level_id(self, obj):
        if obj.role == "student":
            try:
                from students.models import StudentAssessmentAttempt
                latest_attempt = StudentAssessmentAttempt.objects.filter(
                    student=obj, 
                    status="evaluated"
                ).order_by("-evaluated_at").first()
                if latest_attempt:
                    return latest_attempt.template_id
            except Exception:
                pass
        return None

    def get_attempt_id(self, obj):
        if obj.role == "student":
            try:
                from students.models import StudentAssessmentAttempt
                latest_attempt = StudentAssessmentAttempt.objects.filter(
                    student=obj, 
                    status="evaluated"
                ).order_by("-evaluated_at").first()
                if latest_attempt:
                    return latest_attempt.id
            except Exception:
                pass
        return None

    def get_profile(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        
        if obj.role == "student":
            try:
                from students.views import _build_profile_setup_payload
                return _build_profile_setup_payload(request, obj, obj.student_profile)
            except Exception:
                return None
        return None

    class Meta:
        model = User
        fields = ("id", "student_id", "full_name", "email", "role", "is_email_verified", "is_profile_completed", "is_first_assement_completed", "is_location", "expo_push_token", "is_push_notification", "profile", "level_id", "attempt_id")


class PushTokenUpdateSerializer(serializers.Serializer):
    # Blank clears the token (sent by the app on logout).
    expo_push_token = serializers.CharField(max_length=255, allow_blank=True)


class TogglePushNotificationSerializer(serializers.Serializer):
    is_push_notification = serializers.BooleanField()


class SignUpSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        return value.lower()


class SignInSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.lower()


class OtpVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=4, max_length=4)

    def validate_email(self, value):
        return value.lower()

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must be a 4 digit number.")
        return value


class ResendOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(choices=[OtpPurpose.SIGNUP, OtpPurpose.FORGOT_PASSWORD])

    def validate_email(self, value):
        return value.lower()


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class AuthTokensSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access = serializers.CharField()


class TokenRefreshDataSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(required=False)


class SignUpResponseDataSerializer(serializers.Serializer):
    user = UserSerializer()
    next_step = serializers.CharField()


class OtpVerifiedResponseDataSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = AuthTokensSerializer()
    is_profile_completed = serializers.BooleanField()


class SuccessMessageResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()


class SignUpSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = SignUpResponseDataSerializer()


class SignInSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = OtpVerifiedResponseDataSerializer()


class OtpVerifiedSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = OtpVerifiedResponseDataSerializer()


class MeSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = UserSerializer()


class TokenRefreshSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = TokenRefreshDataSerializer()


class ErrorResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=False)
    message = serializers.CharField()
    errors = serializers.JSONField(required=False)


class ForgotPasswordRequestOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower()


class ForgotPasswordVerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=4, max_length=4)

    def validate_email(self, value):
        return value.lower()

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must be a 4 digit number.")
        return value


class ForgotPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        return value.lower()

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Confirm password does not match new password."})
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Confirm password does not match new password."})
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
