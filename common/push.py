"""
Expo push notifications.

Expo answers HTTP 200 even when a notification is rejected, so success has to be
read from the per-message "tickets". Delivery problems that happen later (for
example missing FCM credentials on EAS -> "InvalidCredentials") only show up in
"receipts", which are available a few seconds after sending.
"""
import logging
import time

import requests

logger = logging.getLogger(__name__)

EXPO_SEND_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
}

# Human-readable hints for the errors Expo returns in tickets and receipts.
ERROR_HINTS = {
    "DeviceNotRegistered": "The app was uninstalled or the token is stale. Open the app and log in again to register a new token.",
    "InvalidCredentials": "Push credentials are missing or wrong. Upload the FCM V1 service-account key for com.study.pulse "
                          "to EAS (eas credentials -> Android -> Google Service Account -> FCM V1).",
    "MessageTooBig": "The notification payload is larger than 4096 bytes.",
    "MessageRateExceeded": "Too many notifications sent to this device; slow down.",
    "MismatchSenderId": "google-services.json in the app build belongs to a different Firebase project than the FCM key on EAS.",
}


def is_expo_token(token) -> bool:
    return isinstance(token, str) and (
        token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")
    ) and token.endswith("]")


def send_push(tokens, title, body, data=None, sound="default", channel_id="default"):
    """
    Send one notification to each token.

    Returns a list of {"token", "status", "id", "error", "message"} - one per token,
    in order. Never raises; network errors are reported as status "error".
    Tokens Expo reports as DeviceNotRegistered are cleared from their users.
    """
    if isinstance(tokens, str):
        tokens = [tokens]
    tokens = [t for t in (tokens or []) if t]
    if not tokens:
        return []

    messages = []
    for token in tokens:
        message = {"to": token, "title": title, "body": body, "sound": sound, "channelId": channel_id}
        if data:
            message["data"] = data
        messages.append(message)

    results = []
    # Expo accepts at most 100 messages per request.
    for start in range(0, len(messages), 100):
        chunk = messages[start:start + 100]
        try:
            response = requests.post(EXPO_SEND_URL, json=chunk, headers=_HEADERS, timeout=10)
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Expo push request failed: %s", exc)
            results.extend(
                {"token": m["to"], "status": "error", "id": None, "error": "RequestFailed", "message": str(exc)}
                for m in chunk
            )
            continue

        if response.status_code >= 400 or "errors" in payload:
            error = (payload.get("errors") or [{}])[0]
            message = error.get("message") or f"HTTP {response.status_code}"
            logger.warning("Expo push rejected the request: %s", message)
            results.extend(
                {"token": m["to"], "status": "error", "id": None, "error": error.get("code", "RequestRejected"),
                 "message": message}
                for m in chunk
            )
            continue

        tickets = payload.get("data") or []
        for msg, ticket in zip(chunk, tickets):
            details = ticket.get("details") or {}
            results.append({
                "token": msg["to"],
                "status": ticket.get("status", "error"),
                "id": ticket.get("id"),
                "error": details.get("error"),
                "message": ticket.get("message"),
            })

    failed = [r for r in results if r["status"] != "ok"]
    for r in failed:
        logger.warning("Push to %s failed: %s %s", r["token"], r["error"], r["message"])
    _forget_tokens([r["token"] for r in failed if r["error"] == "DeviceNotRegistered"])
    return results


def get_receipts(ticket_ids):
    """
    Fetch delivery receipts for ticket ids. Returns {ticket_id: {"status", "error", "message"}}.
    Ids Expo doesn't know yet are missing from the result.
    """
    ticket_ids = [i for i in ticket_ids if i]
    if not ticket_ids:
        return {}
    try:
        response = requests.post(EXPO_RECEIPTS_URL, json={"ids": ticket_ids}, headers=_HEADERS, timeout=10)
        receipts = response.json().get("data") or {}
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Fetching Expo receipts failed: %s", exc)
        return {}
    return {
        ticket_id: {
            "status": receipt.get("status"),
            "error": (receipt.get("details") or {}).get("error"),
            "message": receipt.get("message"),
        }
        for ticket_id, receipt in receipts.items()
    }


def send_test_push(token, wait_seconds=5, title="Study Pulse test", body="Push notifications are working 🎉"):
    """
    Send a test notification and, if accepted, wait for its delivery receipt.

    Returns {"ok", "stage", "ticket", "receipt", "hint"}. `stage` is where it ended:
    "token" (not an Expo token), "ticket" (Expo refused it), "receipt" (delivery
    failed or not yet known) or "delivered" (handed to FCM/APNs).
    """
    if not is_expo_token(token):
        return {"ok": False, "stage": "token", "ticket": None, "receipt": None,
                "hint": "No valid Expo push token saved. Open the app on a real device, allow notifications and log in."}

    ticket = send_push(token, title, body, data={"type": "test"})[0]
    if ticket["status"] != "ok":
        return {"ok": False, "stage": "ticket", "ticket": ticket, "receipt": None,
                "hint": ERROR_HINTS.get(ticket["error"], ticket["message"])}

    receipt = None
    deadline = time.monotonic() + max(wait_seconds, 0)
    while wait_seconds > 0:
        time.sleep(min(2, max(deadline - time.monotonic(), 0)))
        receipt = get_receipts([ticket["id"]]).get(ticket["id"])
        if receipt or time.monotonic() >= deadline:
            break

    if receipt is None:
        return {"ok": True, "stage": "receipt", "ticket": ticket, "receipt": None,
                "hint": "Accepted by Expo; the delivery receipt isn't ready yet. If nothing arrives, check again with the ticket id."}
    if receipt["status"] != "ok":
        if receipt["error"] == "DeviceNotRegistered":
            _forget_tokens([token])
        return {"ok": False, "stage": "receipt", "ticket": ticket, "receipt": receipt,
                "hint": ERROR_HINTS.get(receipt["error"], receipt["message"])}
    return {"ok": True, "stage": "delivered", "ticket": ticket, "receipt": receipt,
            "hint": "Delivered to FCM/APNs. If the phone shows nothing, check the app's notification permission and battery settings."}


def _forget_tokens(tokens):
    if not tokens:
        return
    from accounts.models import User  # avoid an import cycle at module load

    cleared = User.objects.filter(expo_push_token__in=tokens).update(expo_push_token=None)
    if cleared:
        logger.info("Cleared %s unregistered push token(s).", cleared)
