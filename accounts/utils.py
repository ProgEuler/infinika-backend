from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

from accounts.models import OneTimePassword, OtpPurpose

OTP_VALID_MINUTES = 10

_PURPOSE_COPY = {
    OtpPurpose.SIGNUP: ("Verify your email", "Use this code to finish creating your Study Pulse account."),
    OtpPurpose.LOGIN: ("Your sign-in code", "Use this code to sign in to Study Pulse."),
    OtpPurpose.FORGOT_PASSWORD: ("Reset your password", "Use this code to reset your Study Pulse password."),
}


def build_otp_email(name: str, code: str, purpose: str):
    """Return (subject, text, html) for an OTP email."""
    heading, intro = _PURPOSE_COPY.get(purpose, ("Your verification code", "Use this code to continue."))
    subject = f"{code} is your Study Pulse code"
    greeting = f"Hello {name}," if name else "Hello,"

    text = (
        f"{greeting}\n\n"
        f"{intro}\n\n"
        f"Your code: {code}\n"
        f"It expires in {OTP_VALID_MINUTES} minutes.\n\n"
        "If you didn't request this, you can ignore this email.\n\n"
        "— Study Pulse"
    )

    html = f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#F7FBFA;font-family:Arial,Helvetica,sans-serif;color:#14171F;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F7FBFA;padding:32px 16px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#FFFFFF;border-radius:16px;border:1px solid #EEF0F3;">
          <tr><td style="padding:32px 32px 8px;">
            <div style="font-size:14px;font-weight:bold;color:#7F3DFF;letter-spacing:0.5px;">STUDY PULSE</div>
            <h1 style="margin:16px 0 8px;font-size:22px;line-height:30px;">{escape(heading)}</h1>
            <p style="margin:0 0 4px;font-size:15px;line-height:22px;color:#4B5563;">{escape(greeting)}</p>
            <p style="margin:0;font-size:15px;line-height:22px;color:#4B5563;">{escape(intro)}</p>
          </td></tr>
          <tr><td align="center" style="padding:24px 32px;">
            <div style="display:inline-block;background:#F1EBFF;border-radius:12px;padding:16px 28px;font-size:34px;font-weight:bold;letter-spacing:10px;color:#7F3DFF;">{escape(code)}</div>
            <p style="margin:12px 0 0;font-size:13px;color:#8E929B;">This code expires in {OTP_VALID_MINUTES} minutes.</p>
          </td></tr>
          <tr><td style="padding:0 32px 32px;">
            <p style="margin:0;font-size:13px;line-height:20px;color:#8E929B;">If you didn't request this code, you can safely ignore this email. Never share it with anyone.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
    return subject, text, html


def _from_email():
    return getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)


def send_code_email(to: str, name: str, code: str, purpose: str, connection=None):
    subject, text, html = build_otp_email(name, code, purpose)
    message = EmailMultiAlternatives(subject, text, _from_email(), [to], connection=connection)
    message.attach_alternative(html, "text/html")
    return message.send(fail_silently=False)


def send_otp_email(otp: OneTimePassword):
    send_code_email(otp.user.email, otp.user.full_name, otp.code, otp.purpose)


def issue_and_send_otp(user, purpose):
    otp = OneTimePassword.issue_for_user(user=user, purpose=purpose, valid_for_minutes=OTP_VALID_MINUTES)
    send_otp_email(otp)
    return otp
