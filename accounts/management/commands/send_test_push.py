"""
Send a test push notification and report exactly where it fails.

    python manage.py send_test_push student@example.com
    python manage.py send_test_push "ExponentPushToken[xxxxxxxx]"
    python manage.py send_test_push --list            # users that have a push token

In Docker:
    docker compose exec web python manage.py send_test_push student@example.com
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from common.push import is_expo_token, send_test_push


class Command(BaseCommand):
    help = "Send a test push notification to a user (by email) or to a raw Expo push token."

    def add_arguments(self, parser):
        parser.add_argument("target", nargs="?", help="User email or ExponentPushToken[...]")
        parser.add_argument("--title", default="Study Pulse test")
        parser.add_argument("--body", default="Push notifications are working 🎉")
        parser.add_argument("--wait", type=int, default=6, help="Seconds to wait for the delivery receipt (default 6).")
        parser.add_argument("--list", action="store_true", help="List users that have a push token saved.")

    def handle(self, *args, target, title, body, wait, list, **options):
        User = get_user_model()
        if list:
            users = User.objects.exclude(expo_push_token__isnull=True).exclude(expo_push_token="").order_by("email")
            if not users:
                self.stdout.write("No users have a push token. Log in from the app on a real device first.")
            for u in users:
                flag = "on " if u.is_push_notification else "off"
                self.stdout.write(f"[{flag}] {u.email:<35} {u.role:<8} {u.expo_push_token}")
            return

        if not target:
            raise CommandError("Give a user email or an Expo push token (or use --list).")

        if is_expo_token(target):
            token, who = target, "raw token"
        else:
            user = User.objects.filter(email=target.lower()).first()
            if user is None:
                raise CommandError(f"No user with email {target}.")
            token, who = user.expo_push_token, user.email
            if not user.is_push_notification:
                self.stdout.write(self.style.WARNING(
                    "Note: this user turned push notifications off in the app; normal notifications skip them."
                ))

        self.stdout.write(f"To    : {who}")
        self.stdout.write(f"Token : {token or '(none saved)'}")

        result = send_test_push(token, wait_seconds=wait, title=title, body=body)
        if result["ticket"]:
            t = result["ticket"]
            self.stdout.write(f"Ticket: {t['status']}" + (f"  id={t['id']}" if t["id"] else "")
                              + (f"  error={t['error']}" if t["error"] else ""))
        if result["receipt"]:
            r = result["receipt"]
            self.stdout.write(f"Receipt: {r['status']}" + (f"  error={r['error']}" if r["error"] else "")
                              + (f"  ({r['message']})" if r["message"] else ""))

        style = self.style.SUCCESS if result["ok"] else self.style.ERROR
        self.stdout.write(style(f"{result['stage'].upper()}: {result['hint']}"))
        if not result["ok"]:
            raise CommandError("Push test failed.")
