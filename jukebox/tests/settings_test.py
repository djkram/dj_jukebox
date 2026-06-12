# Test settings to disable problematic features
import os
from dj_jukebox.settings import *

# CRITICAL: use a separate test database so tests NEVER touch db.sqlite3
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_qa.sqlite3',
        'TEST': {
            'NAME': BASE_DIR / 'test_qa.sqlite3',
        },
    }
}

# pytest-playwright starts an asyncio event loop which triggers Django's
# async safety guard for synchronous ORM calls. Safe to bypass in tests.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

# Provide allauth SocialApp inline so tests don't need a DB SocialApp record.
# Without this the login template raises SocialApp.DoesNotExist → 500.
SOCIALACCOUNT_PROVIDERS = {
    "spotify": {
        "APP": {
            "client_id": "test-spotify-client-id",
            "secret": "test-spotify-secret",
            "key": "",
        }
    },
    "google": {
        "APP": {
            "client_id": "test-google-client-id",
            "secret": "test-google-secret",
            "key": "",
        }
    },
}

# Disable staticfiles manifest storage in tests
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Use simpler password hashers for faster tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable logging in tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null'],
    },
}
