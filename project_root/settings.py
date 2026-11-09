from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
# Defaults to off; set DEBUG=True only in a local .env.
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:8000,http://127.0.0.1:8000",
    cast=Csv(),
)

SECURE_CONTENT_TYPE_NOSNIFF = True
# Turn on once the admin is only reached over HTTPS (it breaks admin login over plain http).
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = config("SECURE_COOKIES", default=False, cast=bool)

# Application definition

INSTALLED_APPS = [
    "unfold",
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'students',
    'teachers',
    'support',
    # framework 
    'rest_framework',
    "drf_spectacular",
      'rest_framework_simplejwt',
]

AUTH_USER_MODEL = "accounts.User"

UNFOLD = {
    "SITE_TITLE": "Study Pulse Admin",
    "SITE_HEADER": "Study Pulse",
    "SITE_SUBHEADER": "Management Dashboard",
    "SITE_SYMBOL": "dashboard",
    "DASHBOARD_CALLBACK": "common.dashboard_views.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "General",
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": "/admin/",
                    },
                    {
                        "title": "Pending Requests",
                        "icon": "notifications",
                        "link": "/admin/teachers/pendingrequest/",
                        "badge": "teachers.utils.get_pending_requests_count",
                    },
                ],
            },
            {
                "title": "Accounts",
                "items": [
                    {
                        "title": "Users",
                        "icon": "group",
                        "link": "/admin/accounts/user/",
                    },
                    {
                        "title": "One Time Passwords",
                        "icon": "vpn_key",
                        "link": "/admin/accounts/onetimepassword/",
                    },
                ],
            },
            {
                "title": "Students",
                "items": [
                    {
                        "title": "Student Profiles",
                        "icon": "person",
                        "link": "/admin/students/studentprofile/",
                    },
                    {
                        "title": "Assessment Templates",
                        "icon": "assignment",
                        "link": "/admin/students/assessmenttemplate/",
                    },
                    {
                        "title": "Assessment Questions",
                        "icon": "quiz",
                        "link": "/admin/students/assessmentquestion/",
                    },
                    
                    {
                        "title": "Student Assessment Attempts",
                        "icon": "history_edu",
                        "link": "/admin/students/studentassessmentattempt/",
                    },
                    {
                        "title": "Interest Summaries",
                        "icon": "auto_awesome",
                        "link": "/admin/students/interestsummary/",
                    },
                    {
                        "title": "Student Locations",
                        "icon": "location_on",
                        "link": "/admin/students/studentlocation/",
                    },
                ],
            },
            {
                "title": "Teachers",
                "items": [
                    {
                        "title": "Teachers List",
                        "icon": "school",
                        "link": "/admin/teachers/teacher/",
                    },
                    {
                        "title": "Teacher Profiles",
                        "icon": "badge",
                        "link": "/admin/teachers/teacherprofile/",
                    },
                    {
                        "title": "Teacher Availabilities",
                        "icon": "event_available",
                        "link": "/admin/teachers/teacheravailability/",
                    },
                    {
                        "title": "Teacher Slots",
                        "icon": "schedule",
                        "link": "/admin/teachers/teacherslot/",
                    },
                    {
                        "title": "Student Bookings",
                        "icon": "book_online",
                        "link": "/admin/teachers/studentbooking/",
                    },
                    {
                        "title": "Teachers Locations",
                        "icon": "location_on",
                        "link": "/admin/teachers/teacherslocation/",
                    },
                    {
                        "title": "Promotional Banner",
                        "icon": "menu_book",
                        "link": "/admin/students/recommendedcourse/",
                    },
                    {
                        "title": "Session List",
                        "icon": "view_list",
                        "link": "/admin/teachers/sessionlist/",
                    },
                    {
                        "title": "Course Modules",
                        "icon": "view_module",
                        "link": "/admin/teachers/coursemodule/",
                    },
                    {
                        "title": "General Info",
                        "icon": "info",
                        "link": "/admin/teachers/generalinfo/",
                    },
                ],
            },
            {
                "title": "Support",
                "items": [
                    {
                        "title": "Policies",
                        "icon": "policy",
                        "link": "/admin/support/policy/",
                    },
                    {
                        "title": "Help & Support",
                        "icon": "support_agent",
                        "link": "/admin/support/helpsupport/",
                    },
                    {
                        "title": "Play Store QR Codes",
                        "icon": "qr_code_2",
                        "link": "/admin/support/playstoreqrcode/",
                    },
                ],
            },
        ],
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Study Pulse API",
    "DESCRIPTION": "API documentation",
    "VERSION": "1.0.0",
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
    },
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}



MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'project_root.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'teachers.context_processors.pending_requests_count',
            ],
        },
    },
]


REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Secure by default: public endpoints opt in with @permission_classes([AllowAny]).
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # Number of reverse proxies (nginx, Cloudflare...) in front of gunicorn, so
    # throttles key on the real client IP instead of a spoofable X-Forwarded-For.
    "NUM_PROXIES": config("NUM_PROXIES", default=1, cast=int),
    "DEFAULT_THROTTLE_RATES": {
        "sign_in": "10/min",
        "sign_up": "10/hour",
        "otp_send_ip": "20/hour",
        "otp_send_email": "5/hour",
        "otp_verify_ip": "20/hour",
        "otp_verify_email": "10/hour",
        "test_push": "10/hour",
    },
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'EXCEPTION_HANDLER': 'common.exceptions.custom_exception_handler',
}


SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=10),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
    'SLIDING_TOKEN_LIFETIME': timedelta(days=30),
    'SLIDING_TOKEN_REFRESH_LIFETIME_LATE_USER': timedelta(days=1),
    'SLIDING_TOKEN_LIFETIME_LATE_USER': timedelta(days=30),
}







# Email
# With RESEND_API_KEY set, all mail goes through Resend's HTTPS API and the
# SMTP settings below are ignored. Without it, EMAIL_BACKEND decides (default:
# print emails to the console/logs instead of sending them).
RESEND_API_KEY = config("RESEND_API_KEY", default="")
if RESEND_API_KEY:
    EMAIL_BACKEND = "common.email_backends.ResendEmailBackend"
else:
    EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Study Pulse <onboarding@resend.dev>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# SMTP (only used when EMAIL_BACKEND is the SMTP backend)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = 15








WSGI_APPLICATION = 'project_root.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }




DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE"),
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST"),
        "PORT": config("DB_PORT"),
        "OPTIONS": {
            "options": f"-c search_path={config('DB_SCHEMA', default='public')}",
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Dhaka'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Shared across gunicorn workers (LocMem is per-process). Needed for auth
# throttles and the forgot-password "OTP verified" flag. The table is created
# by accounts migration 0008.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Django only serves /media/ itself while this is on. Turn it off once nginx
# (or object storage) serves uploads.
SERVE_MEDIA = config("SERVE_MEDIA", default=True, cast=bool)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
