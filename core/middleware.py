"""Middleware that keeps browser-facing pages pinned to English."""

from __future__ import annotations

from django.conf import settings
from django.utils import translation


class ForceEnglishMiddleware:
    """Force Django's active language and response headers to English."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.language_code = getattr(settings, "LANGUAGE_CODE", "en-us")

    def __call__(self, request):
        with translation.override(self.language_code):
            request.LANGUAGE_CODE = translation.get_language()
            response = self.get_response(request)
            if hasattr(response, "render") and callable(response.render):
                response = response.render()

        response.headers.setdefault("Content-Language", self.language_code)
        return response
