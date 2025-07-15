from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('dj/', views.dj_backoffice, name='dj_backoffice'),
    path('login/', auth_views.LoginView.as_view(template_name='jukebox/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='main'), name='logout'),
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),

    # NOVES RUTES
    path('select-party/', views.select_party, name='select_party'),
    path('set-party/<int:party_id>/', views.set_party, name='set_party'),
    path('unset-party/', views.unset_party, name='unset_party'),
    path('party/<int:party_id>/settings/remove_playlist/', views.remove_playlist, name='remove_playlist'),
    path('party/<int:party_id>/settings/', views.party_settings, name='party_settings'),
    path('get_spotify_playlists/', views.get_spotify_playlists, name='get_spotify_playlists'),


    # RUTA per a la llista de cançons de la festa seleccionada
    path('songs/', views.song_list, name='song_list'),

    path('buttons/', views.buttons, name='buttons'),
    path('cards/', views.cards, name='cards'),
    path('charts/', views.charts, name='charts'),
    path('tables/', views.tables, name='tables'),
    # path('login/', views.login, name='login'),
    # path('register/', views.register, name='register'),
    path('forgot-password/', views.forgot_password, name='forgot-password'),
    path('blank/', views.blank, name='blank'),
    path('404/', views.page_404, name='404'),
    path('utilities-color/', views.utilities_color, name='utilities-color'),
    path('utilities-border/', views.utilities_border, name='utilities-border'),
    path('utilities-animation/', views.utilities_animation, name='utilities-animation'),
    path('utilities-other/', views.utilities_other, name='utilities-other'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "jukebox" / "static")
