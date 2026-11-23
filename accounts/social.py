"""
Google / Apple sign-in (same flow as PetNabor).

The app signs in natively with Google or Apple, exchanges that for a Firebase
user, and sends the Firebase ID token here. We verify it with Firebase Admin,
then find, link or create the Study Pulse user. Social sign-in is both log in
and sign up: a new email gets a fresh, already-verified student account.
"""

import hashlib
import hmac
import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from accounts.models import UserRole
from common.firebase import FirebaseNotConfigured, verify_id_token

User = get_user_model()
logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = {"google.com", "apple.com"}


class SocialLoginError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _check_apple_nonce(firebase_data, nonce):
    token_nonce = (firebase_data.get("sign_in_attributes") or {}).get("nonce")
    if not token_nonce:
        return
    if not nonce:
        raise SocialLoginError("Nonce is required for Apple Sign-In verification.", 401)
    hashed = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    # The app may send the raw nonce or its hash.
    if not (hmac.compare_digest(nonce, token_nonce) or hmac.compare_digest(hashed, token_nonce)):
        raise SocialLoginError("Invalid nonce for Apple Sign-In.", 401)


def firebase_login(id_token, full_name="", nonce=""):
    """
    Returns (user, is_new_user). Raises SocialLoginError with a user-facing message.
    """
    try:
        decoded = verify_id_token(id_token)
    except FirebaseNotConfigured:
        logger.error("Social sign-in attempted but Firebase credentials are not configured.")
        raise SocialLoginError("Google and Apple sign-in are not available right now.", 503)
    except Exception as exc:  # noqa: BLE001 - firebase raises several token error types
        logger.warning("Firebase token verification failed: %s", exc)
        raise SocialLoginError("Invalid sign-in token. Please try again.", 401)

    firebase_data = decoded.get("firebase") or {}
    provider = firebase_data.get("sign_in_provider", "")
    if provider not in SUPPORTED_PROVIDERS:
        raise SocialLoginError("Unsupported sign-in method.", 401)
    if provider == "apple.com":
        _check_apple_nonce(firebase_data, nonce)

    uid = decoded.get("uid")
    email = (decoded.get("email") or "").strip().lower()
    email_verified = bool(decoded.get("email_verified"))
    name = (full_name or decoded.get("name") or "").strip()

    if not uid:
        raise SocialLoginError("Invalid sign-in token.", 401)
    if not email:
        raise SocialLoginError("Your Google/Apple account did not share an email address.", 400)

    with transaction.atomic():
        user = User.objects.select_for_update().filter(firebase_uid=uid).first()
        linking = False
        if user is None:
            user = User.objects.select_for_update().filter(email__iexact=email).first()
            linking = user is not None

        if user is not None:
            if user.role == UserRole.ADMIN:
                raise SocialLoginError("This account can't be used in the app. Please use the admin panel.", 403)
            if user.is_email_verified and not user.is_active:
                raise SocialLoginError("This account has been deactivated. Please contact support.", 403)

        if user is not None and linking:
            # Joining Google/Apple to an existing email account is only safe when
            # the provider proved the user owns that address.
            if not email_verified:
                raise SocialLoginError(
                    "An account with this email already exists. Please sign in with your email and password.",
                    409,
                )
            update_fields = ["firebase_uid", "updated_at"]
            if not user.is_email_verified:
                # Unfinished email sign-up: whoever started it may not own the
                # address. Drop their password so only the proven owner gets in.
                user.set_unusable_password()
                user.is_email_verified = True
                user.is_active = True
                update_fields += ["password", "is_email_verified", "is_active"]
                if name:
                    user.full_name = name
                    update_fields.append("full_name")
            user.firebase_uid = uid
            user.save(update_fields=update_fields)

        if user is not None:
            return user, False

        user = User.objects.create_user(
            email=email,
            full_name=name or email.split("@")[0],
            password=None,  # unusable; "Forgot password" can set one later
            role=UserRole.STUDENT,
            is_active=True,
            is_email_verified=True,
            firebase_uid=uid,
        )
        return user, True
