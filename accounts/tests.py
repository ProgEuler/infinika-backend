from django.core import mail
from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import OneTimePassword, OtpPurpose, User, UserRole


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthenticationFlowTests(APITestCase):
    def test_student_signup_creates_inactive_user_and_sends_otp(self):
        response = self.client.post(
            "/api/accounts/sign-up/",
            {
                "full_name": "John Student",
                "email": "john@example.com",
                "password": "StrongPass123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="john@example.com")
        self.assertEqual(user.role, UserRole.STUDENT)
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertEqual(OneTimePassword.objects.filter(user=user, purpose=OtpPurpose.SIGNUP).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_signup_otp_verification_returns_jwt_tokens(self):
        user = User.objects.create_user(
            email="verify@example.com",
            full_name="Verify Student",
            password="StrongPass123",
            role=UserRole.STUDENT,
            is_active=False,
            is_email_verified=False,
        )
        otp = OneTimePassword.issue_for_user(user, OtpPurpose.SIGNUP)

        response = self.client.post(
            "/api/accounts/verify-sign-up-otp/",
            {"email": user.email, "otp": otp.code},
            format="json",
        )

        user.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertIn("access", response.data["data"]["tokens"])
        self.assertIn("refresh", response.data["data"]["tokens"])

    def test_sign_in_returns_jwt_tokens_for_verified_user(self):
        user = User.objects.create_user(
            email="teacher@example.com",
            full_name="Teacher User",
            password="StrongPass123",
            role=UserRole.TEACHER,
            is_active=True,
            is_email_verified=True,
        )

        sign_in_response = self.client.post(
            "/api/accounts/sign-in/",
            {"email": user.email, "password": "StrongPass123"},
            format="json",
        )

        self.assertEqual(sign_in_response.status_code, status.HTTP_200_OK)
        self.assertEqual(sign_in_response.data["data"]["user"]["role"], UserRole.TEACHER)
        self.assertIn("access", sign_in_response.data["data"]["tokens"])
        self.assertIn("refresh", sign_in_response.data["data"]["tokens"])
        self.assertFalse(OneTimePassword.objects.filter(user=user, purpose=OtpPurpose.LOGIN).exists())


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OtpBruteForceProtectionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="victim@example.com",
            full_name="Victim",
            password="StrongPass123",
            is_active=True,
            is_email_verified=True,
        )

    def _wrong_code(self, otp):
        return "1000" if otp.code != "1000" else "1001"

    def test_otp_is_burned_after_max_failed_attempts(self):
        otp = OneTimePassword.issue_for_user(self.user, OtpPurpose.FORGOT_PASSWORD)
        for _ in range(OneTimePassword.MAX_FAILED_ATTEMPTS):
            r = self.client.post(
                "/api/accounts/forgot-password/verify-otp/",
                {"email": self.user.email, "otp": self._wrong_code(otp)},
                format="json",
            )
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

        # The correct code no longer works once the OTP is burned.
        r = self.client.post(
            "/api/accounts/forgot-password/verify-otp/",
            {"email": self.user.email, "otp": otp.code},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)
        self.assertEqual(otp.failed_attempts, OneTimePassword.MAX_FAILED_ATTEMPTS)

    def test_correct_code_after_a_few_mistakes_still_works(self):
        otp = OneTimePassword.issue_for_user(self.user, OtpPurpose.FORGOT_PASSWORD)
        self.client.post(
            "/api/accounts/forgot-password/verify-otp/",
            {"email": self.user.email, "otp": self._wrong_code(otp)},
            format="json",
        )
        r = self.client.post(
            "/api/accounts/forgot-password/verify-otp/",
            {"email": self.user.email, "otp": otp.code},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        r = self.client.post(
            "/api/accounts/forgot-password/reset/",
            {"email": self.user.email, "new_password": "NewStrong456", "confirm_password": "NewStrong456"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrong456"))

    def test_reset_without_verified_otp_is_rejected(self):
        r = self.client.post(
            "/api/accounts/forgot-password/reset/",
            {"email": self.user.email, "new_password": "NewStrong456", "confirm_password": "NewStrong456"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_forgot_password_does_not_reveal_unknown_emails(self):
        known = self.client.post(
            "/api/accounts/forgot-password/request-otp/", {"email": self.user.email}, format="json"
        )
        unknown = self.client.post(
            "/api/accounts/forgot-password/request-otp/", {"email": "nobody@example.com"}, format="json"
        )
        self.assertEqual(known.status_code, status.HTTP_200_OK)
        self.assertEqual(unknown.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_otp_requests_are_rate_limited_per_email(self):
        codes = [
            self.client.post(
                "/api/accounts/forgot-password/request-otp/", {"email": self.user.email}, format="json"
            ).status_code
            for _ in range(6)
        ]
        self.assertEqual(codes[:5], [status.HTTP_200_OK] * 5)
        self.assertEqual(codes[5], status.HTTP_429_TOO_MANY_REQUESTS)


class SecureDefaultsTests(APITestCase):
    def test_api_requires_auth_by_default(self):
        r = self.client.get("/api/teachers/available-slots/?date=2030-01-07")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
