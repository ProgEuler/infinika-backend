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


def send_expo_push_notification(push_tokens, title, body, data=None):
    """
    Send push notifications through Expo. Returns one result per token
    (see common.push.send_push); failures are logged, never raised.
    """
    from .push import send_push

    return send_push(push_tokens, title, body, data=data)


def use_success(data=None, message="Success"):
    return success_response(data=data, message=message)


def use_error(message="Error", errors=None):
    return error_response(message=message, errors=errors)
