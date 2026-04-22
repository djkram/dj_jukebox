from django.conf import settings


class DefaultLanguageMiddleware:
    """Força el català com a idioma per defecte quan no hi ha cap cookie d'idioma."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME):
            request.META['HTTP_ACCEPT_LANGUAGE'] = 'ca'
        return self.get_response(request)
