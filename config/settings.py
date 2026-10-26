import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-a-secret")

ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".onrender.com"]
ALLOWED_HOSTS += [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]

# No database, sessions or admin: the API is stateless.
INSTALLED_APPS = []
DATABASES = {}
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
USE_TZ = True

# The built React app is served by WhiteNoise from the same origin as the API.
WHITENOISE_ROOT = BASE_DIR / "frontend" / "dist"
WHITENOISE_INDEX_FILE = True

# OpenStreetMap's tile servers reject requests that carry no Referer, and
# Django's default policy (same-origin) strips it on cross-origin requests.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
