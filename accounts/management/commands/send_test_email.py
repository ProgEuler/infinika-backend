"""
Send a test OTP email to check that outgoing mail (e.g. Resend) works.

    python manage.py send_test_email you@example.com
    python manage.py send_test_email you@example.com --purpose forgot_password
    python manage.py send_test_email student@example.com --real   # issue a real, usable OTP

In Docker:
    docker compose exec web python manage.py send_test_email you@example.com
"""
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import get_connection
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from accounts.models import OneTimePassword, OtpPurpose
from accounts.utils import OTP_VALID_MINUTES, send_code_email


class Command(BaseCommand):
    help = "Send a test OTP email to verify the email configuration."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Recipient email address")
        parser.add_argument(
            "--purpose",
            choices=[p.value for p in OtpPurpose],
            default=OtpPurpose.SIGNUP,
            help="Which OTP email template to send (default: signup).",
        )
        parser.add_argument(
            "--real",
            action="store_true",
            help="Issue a real OTP for the existing user with this email, usable in the app.",
        )

    def handle(self, *args, to, purpose, real, **options):
        try:
            validate_email(to)
        except ValidationError:
            raise CommandError(f"'{to}' is not a valid email address.")

        name = "Test User"
        if real:
            user = get_user_model().objects.filter(email=to.lower()).first()
            if user is None:
                raise CommandError(f"No user with email {to}; --real needs an existing account.")
            otp = OneTimePassword.issue_for_user(user=user, purpose=purpose, valid_for_minutes=OTP_VALID_MINUTES)
            code, name = otp.code, user.full_name
        else:
            code = f"{secrets.randbelow(9000) + 1000:04d}"

        self.stdout.write(f"Backend : {settings.EMAIL_BACKEND}")
        self.stdout.write(f"From    : {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"To      : {to}  (purpose={purpose}, {'real OTP' if real else 'sample code'})")

        connection = get_connection(fail_silently=False)
        try:
            sent = send_code_email(to, name, code, purpose, connection=connection)
        except Exception as exc:
            raise CommandError(f"Sending failed: {exc}") from exc

        if not sent:
            raise CommandError("The email backend reported 0 messages sent.")
        message_id = getattr(connection, "last_message_id", None)
        self.stdout.write(self.style.SUCCESS(
            f"Sent. Code: {code}" + (f"  Resend id: {message_id}" if message_id else "")
        ))
