from datetime import datetime

from django.shortcuts import render
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from common.responses import success_response, error_response
from support.models import Policy, HelpSupport, PlayStoreQRCode

from support.serializers import PolicySerializer, HelpSupportSerializer, PlayStoreQRCodeSerializer


# ── Public HTML pages (not API) ──────────────────────────────────

def privacy_policy_page(request):
    policies = Policy.objects.all()
    return render(request, "pages/privacy_policy.html", {
        "policies": policies,
        "year": datetime.now().year,
    })


def delete_account_page(request):
    return render(request, "pages/delete_account.html", {
        "year": datetime.now().year,
    })


# ── API views ────────────────────────────────────────────────────

@extend_schema(
    tags=["Support & Policies"],
    operation_id="support_policy",
    responses={200: PolicySerializer(many=True)},
    description="Fetch app policies.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def policy_view(request):
    policies = Policy.objects.all()
    serializer = PolicySerializer(policies, many=True)
    return success_response(serializer.data, message="Policies fetched successfully.")


@extend_schema(
    tags=["Support & Policies"],
    operation_id="support_help_support",
    responses={200: HelpSupportSerializer},
    description="Fetch help and support contact info.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def help_support_view(request):
    support = HelpSupport.objects.first()
    if not support:
        return error_response("Support info not configured.", status_code=status.HTTP_404_NOT_FOUND)
    serializer = HelpSupportSerializer(support)
    return success_response(serializer.data, message="Help & support info fetched successfully.")


@extend_schema(
    tags=["Support & Policies"],
    operation_id="support_play_store_qr",
    responses={200: PlayStoreQRCodeSerializer},
    description="Fetch Play Store QR Code PDF.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def play_store_qr_view(request):
    qr_code = PlayStoreQRCode.objects.first()
    if not qr_code:
        return error_response("QR Code not found.", status_code=status.HTTP_404_NOT_FOUND)
    serializer = PlayStoreQRCodeSerializer(qr_code)
    return success_response(serializer.data, message="QR Code fetched successfully.")
