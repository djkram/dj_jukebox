import time

from django.conf import settings
from django.core.cache import cache


class DefaultLanguageMiddleware:
    """Força el català com a idioma per defecte quan no hi ha cap cookie d'idioma."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME):
            request.META['HTTP_ACCEPT_LANGUAGE'] = 'ca'
        return self.get_response(request)


class ResponseTimingMiddleware:
    """Acumula els temps de resposta de les pàgines al cache per al monitoring."""

    _CACHE_KEY = '_mon_resp_times'
    _MAX_SAMPLES = 100
    _SKIP_PREFIXES = ('/static/', '/admin/', '/stripe/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if any(path.startswith(p) for p in self._SKIP_PREFIXES):
            return self.get_response(request)

        t0 = time.monotonic()
        response = self.get_response(request)
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

        try:
            samples = cache.get(self._CACHE_KEY) or []
            samples.append(elapsed_ms)
            if len(samples) > self._MAX_SAMPLES:
                samples = samples[-self._MAX_SAMPLES:]
            cache.set(self._CACHE_KEY, samples, 3600)
        except Exception:
            pass

        return response
