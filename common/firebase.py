"""
Firebase Admin, used only to verify ID tokens from Google / Apple sign-in.

Initialised lazily on first use so the app (and tests) start fine without the
service-account file. Put the key (Firebase console > Project settings >
Service accounts > Generate new private key) at settings.FIREBASE_CREDENTIALS.
"""

import logging
import os
import threading

from django.conf import settings

logger = logging.getLogger(__name__)
_lock = threading.Lock()


class FirebaseNotConfigured(Exception):
    pass


def _app():
    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        return firebase_admin.get_app()
    with _lock:
        if firebase_admin._apps:
            return firebase_admin.get_app()
        path = settings.FIREBASE_CREDENTIALS
        if not path or not os.path.exists(path):
            raise FirebaseNotConfigured(f"Firebase credentials file not found: {path}")
        return firebase_admin.initialize_app(credentials.Certificate(path))


def verify_id_token(id_token):
    """Return the decoded Firebase ID token. Raises on an invalid/expired token."""
    from firebase_admin import auth

    return auth.verify_id_token(id_token, app=_app())


def delete_firebase_user(uid):
    """Best effort: remove the Firebase Auth user when the account is deleted."""
    if not uid:
        return
    try:
        from firebase_admin import auth

        auth.delete_user(uid, app=_app())
    except Exception:  # noqa: BLE001 - never block account deletion on Firebase
        logger.warning("Could not delete Firebase user %s", uid, exc_info=True)
