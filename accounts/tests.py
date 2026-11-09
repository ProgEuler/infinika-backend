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


class ChangePasswordAndPushTokenTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="student@example.com", full_name="Student", password="StrongPass123"
        )
        self.client.force_authenticate(self.user)

    def test_change_password_requires_correct_current_password(self):
        r = self.client.post(
            "/api/accounts/change-password/",
            {"current_password": "wrong", "new_password": "NewStrong456", "confirm_password": "NewStrong456"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("current_password", r.data["errors"])

    def test_change_password_success(self):
        r = self.client.post(
            "/api/accounts/change-password/",
            {"current_password": "StrongPass123", "new_password": "NewStrong456", "confirm_password": "NewStrong456"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrong456"))

    def test_push_token_moves_between_accounts_and_can_be_cleared(self):
        other = User.objects.create_user(email="other@example.com", full_name="Other", password="x" * 10)
        other.expo_push_token = "ExponentPushToken[abc]"
        other.save()

        r = self.client.post("/api/accounts/update-push-token/", {"expo_push_token": "ExponentPushToken[abc]"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        other.refresh_from_db()
        self.user.refresh_from_db()
        self.assertIsNone(other.expo_push_token)
        self.assertEqual(self.user.expo_push_token, "ExponentPushToken[abc]")

        r = self.client.post("/api/accounts/update-push-token/", {"expo_push_token": ""}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.expo_push_token)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ResendOtpTests(APITestCase):
    def test_resend_works_for_forgot_password(self):
        user = User.objects.create_user(email="r@example.com", full_name="R", password="StrongPass123")
        r = self.client.post(
            "/api/accounts/resend-otp/", {"email": user.email, "purpose": "forgot_password"}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(OneTimePassword.objects.filter(user=user, purpose=OtpPurpose.FORGOT_PASSWORD).count(), 1)
        self.assertEqual(len(mail.outbox), 1)


class ResendBackendTests(APITestCase):
    def _backend(self):
        from common.email_backends import ResendEmailBackend

        return ResendEmailBackend(api_key="re_test_key")

    def test_sends_text_and_html_to_resend_api(self):
        from unittest import mock

        from django.core.mail import EmailMultiAlternatives

        msg = EmailMultiAlternatives("Hi", "plain body", "Study Pulse <no-reply@example.com>", ["a@example.com"])
        msg.attach_alternative("<b>html body</b>", "text/html")
        backend = self._backend()
        fake = mock.Mock(status_code=200)
        fake.json.return_value = {"id": "email_123"}
        with mock.patch("requests.Session.post", return_value=fake) as post:
            self.assertEqual(backend.send_messages([msg]), 1)

        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        self.assertEqual(url, "https://api.resend.com/emails")
        self.assertEqual(payload["to"], ["a@example.com"])
        self.assertEqual(payload["from"], "Study Pulse <no-reply@example.com>")
        self.assertEqual(payload["text"], "plain body")
        self.assertEqual(payload["html"], "<b>html body</b>")
        self.assertEqual(backend.last_message_id, "email_123")

    def test_api_error_raises_with_resend_message(self):
        from unittest import mock

        from django.core.mail import EmailMessage

        from common.email_backends import ResendError

        fake = mock.Mock(status_code=403, text="forbidden")
        fake.json.return_value = {"message": "The yourdomain.com domain is not verified."}
        with mock.patch("requests.Session.post", return_value=fake):
            with self.assertRaisesMessage(ResendError, "domain is not verified"):
                self._backend().send_messages([EmailMessage("s", "b", "x@example.com", ["a@example.com"])])

    def test_missing_api_key_is_a_clear_error(self):
        from django.core.exceptions import ImproperlyConfigured
        from django.core.mail import EmailMessage

        from common.email_backends import ResendEmailBackend

        with self.settings(RESEND_API_KEY=""):
            with self.assertRaises(ImproperlyConfigured):
                ResendEmailBackend().send_messages([EmailMessage("s", "b", "x@example.com", ["a@example.com"])])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OtpEmailAndTestCommandTests(APITestCase):
    def test_otp_email_has_code_in_subject_text_and_html(self):
        from accounts.utils import issue_and_send_otp

        user = User.objects.create_user(email="o@example.com", full_name="Aysel", password="StrongPass123")
        otp = issue_and_send_otp(user, OtpPurpose.SIGNUP)
        msg = mail.outbox[0]
        self.assertIn(otp.code, msg.subject)
        self.assertIn(otp.code, msg.body)
        html = msg.alternatives[0][0]
        self.assertIn(otp.code, html)
        self.assertIn("Aysel", html)

    def test_send_test_email_command_sample_code(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("send_test_email", "check@example.com", stdout=out)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["check@example.com"])
        self.assertIn("Sent. Code:", out.getvalue())
        self.assertFalse(OneTimePassword.objects.exists())  # sample mode creates no OTP

    def test_send_test_email_command_real_otp(self):
        from io import StringIO

        from django.core.management import call_command

        user = User.objects.create_user(email="real@example.com", full_name="Real", password="StrongPass123")
        call_command("send_test_email", "real@example.com", "--real", "--purpose", "forgot_password", stdout=StringIO())
        otp = OneTimePassword.objects.get(user=user, purpose=OtpPurpose.FORGOT_PASSWORD, is_used=False)
        self.assertIn(otp.code, mail.outbox[0].subject)

    def test_send_test_email_command_rejects_unknown_user_for_real(self):
        from io import StringIO

        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("send_test_email", "nobody@example.com", "--real", stdout=StringIO())
