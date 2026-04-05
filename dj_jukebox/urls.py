"""
URL configuration for dj_jukebox project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns

# URLs sense prefix d'idioma (necessàries per al canvi d'idioma)
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('accounts/', include('allauth.urls')),
]

# URLs amb prefix d'idioma (ca/, en/, etc.)
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path('', include('jukebox.urls')),
    prefix_default_language=True,  # Afegir prefix fins i tot per l'idioma per defecte
)
