"""
Rate limits for unauthenticated auth endpoints.

DRF's ScopedRateThrottle needs a `throttle_scope` attribute on the view, which
function-based @api_view views can't carry, so each scope gets its own class.
Rates live in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].

These are a second line of defence; the hard limit on OTP guessing is the
per-OTP attempt counter in OneTimePassword.verify().
"""

from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class _IpThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class _EmailThrottle(SimpleRateThrottle):
    """Keyed on the submitted email, so rotating IPs can't flood one inbox."""

    def get_cache_key(self, request, view):
        email = request.data.get("email") if hasattr(request, "data") else None
        if not email or not isinstance(email, str):
            return None  # nothing to key on; the IP throttle still applies
        return self.cache_format % {"scope": self.scope, "ident": email.strip().lower()}


class SignInThrottle(_IpThrottle):
    scope = "sign_in"


class SignUpThrottle(_IpThrottle):
    scope = "sign_up"


class OtpSendIpThrottle(_IpThrottle):
    scope = "otp_send_ip"


class OtpSendEmailThrottle(_EmailThrottle):
    scope = "otp_send_email"


class OtpVerifyIpThrottle(_IpThrottle):
    scope = "otp_verify_ip"


class OtpVerifyEmailThrottle(_EmailThrottle):
    scope = "otp_verify_email"


OTP_SEND_THROTTLES = [OtpSendIpThrottle, OtpSendEmailThrottle]
OTP_VERIFY_THROTTLES = [OtpVerifyIpThrottle, OtpVerifyEmailThrottle]


class TestPushThrottle(UserRateThrottle):
    scope = "test_push"
