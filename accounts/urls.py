from django.urls import path
from accounts import views
app_name = "accounts"

urlpatterns = [
    path("sign-up/", views.sign_up, name="sign_up"),
    path("verify-sign-up-otp/", views.verify_sign_up_otp, name="verify_sign_up_otp"),
    path("sign-in/", views.sign_in, name="sign_in"),
    path("forgot-password/request-otp/", views.forgot_password_request_otp, name="forgot_password_request_otp"),
    path("forgot-password/verify-otp/", views.forgot_password_verify_otp, name="forgot_password_verify_otp"),
    path("forgot-password/reset/", views.forgot_password_reset, name="forgot_password_reset"),
    path("resend-otp/", views.resend_otp, name="resend_otp"),
    path("refresh-token/", views.refresh_token, name="refresh_token"),
    path("update-push-token/", views.update_push_token, name="update_push_token"),
    path("toggle-push-notification/", views.toggle_push_notification, name="toggle_push_notification"),
    path("change-password/", views.change_password, name="change_password"),
    path("delete-account/", views.delete_account, name="delete_account"),
    path("me/", views.me, name="me"),
]

