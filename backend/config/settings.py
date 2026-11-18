import math
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG = os.getenv('DJANGO_DEBUG', '0') == '1'
REQUIRE_EMAIL_VERIFICATION = os.getenv('REQUIRE_EMAIL_VERIFICATION', '1') == '1'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'rest_framework', 'core', 'reference', 'crm', 'inventory', 'sales', 'purchases', 'approvals', 'invoicing', 'dashboard', 'people']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': os.getenv('POSTGRES_DB', 'qavelys'), 'USER': os.getenv('POSTGRES_USER', 'qavelys'), 'PASSWORD': os.environ['POSTGRES_PASSWORD'], 'HOST': os.getenv('POSTGRES_HOST', 'localhost'), 'PORT': os.getenv('POSTGRES_PORT', '5432')}}
DATABASES['default']['OPTIONS'] = {'connect_timeout': 5}
AUTH_USER_MODEL = 'core.User'
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES': ['core.authentication.VerifiedSessionAuthentication'], 'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'], 'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer']}
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'UTC'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_FILE_PATH = os.getenv('EMAIL_FILE_PATH', str(BASE_DIR.parent / '.local' / 'emails'))
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', '0') == '1'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', '0') == '1'
EMAIL_TIMEOUT = float(os.getenv('EMAIL_TIMEOUT', '10'))
if EMAIL_TIMEOUT <= 0 or not math.isfinite(EMAIL_TIMEOUT):
    raise ValueError('EMAIL_TIMEOUT doit être un nombre fini strictement positif.')
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ValueError('EMAIL_USE_TLS et EMAIL_USE_SSL sont mutuellement exclusifs.')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@localhost')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
PASSWORD_RESET_TIMEOUT = 3600
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR.parent / '.local' / 'media')))
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024
