import hmac
import secrets
from datetime import timedelta
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models, transaction
from django.utils import timezone


class UserRole(models.TextChoices):
    STUDENT = "student", "Student"
    TEACHER = "teacher", "Teacher"
    ADMIN = "admin", "Admin"


class OtpPurpose(models.TextChoices):
    SIGNUP = "signup", "Sign Up"
    LOGIN = "login", "Sign In"
    FORGOT_PASSWORD = "forgot_password", "Forgot Password"


class UserManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        if not full_name:
            raise ValueError("Full name is required.")

        email = self.normalize_email(email).lower()
        extra_fields.setdefault("role", UserRole.STUDENT)
        user = self.model(email=email, full_name=full_name.strip(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_email_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, full_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    full_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.STUDENT)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=True)
    is_profile_completed = models.BooleanField(default=False)
    is_first_assement_completed = models.BooleanField(default=False)
    expo_push_token = models.CharField(max_length=255, blank=True, null=True)
    is_push_notification = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"


class OneTimePassword(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    purpose = models.CharField(max_length=20, choices=OtpPurpose.choices)
    MAX_FAILED_ATTEMPTS = 5

    code = models.CharField(max_length=4)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.purpose} - {self.code}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def generate_code(cls):
        return f"{secrets.randbelow(9000) + 1000:04d}"

    @classmethod
    def issue_for_user(cls, user, purpose, valid_for_minutes=10):
        cls.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
        return cls.objects.create(
            user=user,
            purpose=purpose,
            code=cls.generate_code(),
            expires_at=timezone.now() + timedelta(minutes=valid_for_minutes),
        )

    def mark_used(self):
        if not self.is_used:
            self.is_used = True
            self.save(update_fields=["is_used"])

    @classmethod
    def verify(cls, user, purpose, code):
        """
        Check `code` against the user's single active OTP for `purpose`.

        Every wrong guess is counted; after MAX_FAILED_ATTEMPTS the OTP is
        burned and the user must request a new one. This is what stops the
        4-digit code space from being brute-forced. Returns the OTP on
        success (already marked used), otherwise None.
        """
        with transaction.atomic():
            otp = (
                cls.objects.select_for_update()
                .filter(user=user, purpose=purpose, is_used=False)
                .order_by("-created_at")
                .first()
            )
            if otp is None or otp.is_expired:
                return None

            if not hmac.compare_digest(str(otp.code), str(code)):
                otp.failed_attempts += 1
                if otp.failed_attempts >= cls.MAX_FAILED_ATTEMPTS:
                    otp.is_used = True
                otp.save(update_fields=["failed_attempts", "is_used"])
                return None

            otp.is_used = True
            otp.save(update_fields=["is_used"])
            return otp


class AppLanguage(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "language_of_app"
        ordering = ["name"]
        verbose_name = "Language of App"
        verbose_name_plural = "Languages of App"

    def __str__(self):
        return self.name
