"""
WSGI config for the procurement approval system.

Exposes the WSGI callable as module-level variable named ``application``.
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()
