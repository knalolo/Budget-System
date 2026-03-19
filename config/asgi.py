"""
ASGI config for the procurement approval system.

Exposes the ASGI callable as module-level variable named ``application``.
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
