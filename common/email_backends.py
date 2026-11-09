"""
Django email backend that sends through the Resend HTTP API (https://resend.com).

Every `send_mail` / `EmailMessage` in the project goes through it once
EMAIL_BACKEND points here. It uses HTTPS (port 443) rather than SMTP, because
many VPS providers block outbound SMTP ports.

Settings:
    RESEND_API_KEY      re_...  (required)
    DEFAULT_FROM_EMAIL  e.g. "Study Pulse <no-reply@yourdomain.com>"; the domain
                        must be verified in Resend. "onboarding@resend.dev" only
                        delivers to the Resend account owner's own address.
"""
import logging

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class ResendError(Exception):
    """Resend rejected the message or could not be reached."""


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, api_key=None, timeout=None, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = api_key or getattr(settings, "RESEND_API_KEY", "")
        self.timeout = timeout or getattr(settings, "RESEND_TIMEOUT", 10)
        self.session = None
        # Id of the last message Resend accepted (handy for the test command / logs).
        self.last_message_id = None

    def open(self):
        if not self.api_key:
            raise ImproperlyConfigured("RESEND_API_KEY is not set; cannot send email through Resend.")
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update(
                {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            )
            return True
        return False

    def close(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        try:
            created = self.open()
        except ImproperlyConfigured:
            if self.fail_silently:
                return 0
            raise
        sent = 0
        try:
            for message in email_messages:
                try:
                    self._send(message)
                    sent += 1
                except Exception:
                    if not self.fail_silently:
                        raise
                    logger.exception("Resend failed to send email to %s", message.to)
        finally:
            if created:
                self.close()
        return sent

    def _payload(self, message):
        if message.attachments:
            # Not needed by the app today; fail loudly rather than drop files silently.
            raise ResendError("Attachments are not supported by ResendEmailBackend.")

        payload = {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": list(message.to),
            "subject": message.subject,
        }
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)

        html = None
        for content, mimetype in getattr(message, "alternatives", []) or []:
            if mimetype == "text/html":
                html = content
        if getattr(message, "content_subtype", "plain") == "html":
            html = message.body
        else:
            payload["text"] = message.body
        if html:
            payload["html"] = html
        return payload

    def _send(self, message):
        if not message.recipients():
            return
        response = self.session.post(RESEND_API_URL, json=self._payload(message), timeout=self.timeout)
        if response.status_code >= 400:
            try:
                detail = response.json().get("message") or response.text
            except ValueError:
                detail = response.text
            raise ResendError(f"Resend API error {response.status_code}: {detail}")
        self.last_message_id = (response.json() or {}).get("id")
        logger.info("Resend accepted email %s to %s", self.last_message_id, message.to)
