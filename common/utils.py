import logging
"""Reusable helpers for API operations."""

from .responses import success_response, error_response



logger = logging.getLogger(__name__)

def format_validation_errors(errors):
    if not errors:
        return []
    if isinstance(errors, dict):
        return [{"field": k, "errors": v} for k, v in errors.items()]
    return list(errors)


def bool_to_yes_no(value: bool) -> str:
    return "yes" if value else "no"


import requests


def send_expo_push_notification(push_tokens, title, body, data=None):
    """
    Send push notifications using Expo's Push API.
    push_tokens: List of strings or a single string
    title: String
    body: String
    data: Optional dict
    """
    if not push_tokens:
        return None
    
    if isinstance(push_tokens, str):
        push_tokens = [push_tokens]
    
    # Filter out empty or null tokens
    push_tokens = [token for token in push_tokens if token]
    if not push_tokens:
        return None

    url = "https://exp.host/--/api/v2/push/send"
    
    messages = []
    for token in push_tokens:
        message = {
            "to": token,
            "title": title,
            "body": body,
        }
        if data:
            message["data"] = data
        messages.append(message)

    try:
        response = requests.post(
            url,
            json=messages,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-encoding": "gzip, deflate",
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning("Error sending push notification: %s", e)
        return None


def use_success(data=None, message="Success"):
    return success_response(data=data, message=message)


def use_error(message="Error", errors=None):
    return error_response(message=message, errors=errors)
