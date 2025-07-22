from django.views.generic import RedirectView
from django.urls import path, include, reverse_lazy
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from .views import stripe_webhook
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('dj/', views.dj_backoffice, name='dj_backoffice'),
    path('dj/dashboard/', views.dj_dashboard, name='dj_dashboard'),
    path('dj/mark_played/<int:song_id>/', views.mark_song_played, name='mark_song_played'),
    
    path('login/', RedirectView.as_view(url=reverse_lazy('account_login'), permanent=False)),
    path('register/', RedirectView.as_view(url=reverse_lazy('account_signup'), permanent=False)),
    path('profile/', views.profile, name='profile'),
    path('logout/', auth_views.LogoutView.as_view(next_page='main'), name='logout'),

    # NOVES RUTES
    path('select-party/', views.select_party, name='select_party'),
    path('set-party/<int:party_id>/', views.set_party, name='set_party'),
    path('unset-party/', views.unset_party, name='unset_party'),
    path('party/<int:party_id>/settings/remove_playlist/', views.remove_playlist, name='remove_playlist'),
    path('party/<int:party_id>/settings/', views.party_settings, name='party_settings'),
    path('get_spotify_playlists/', views.get_spotify_playlists, name='get_spotify_playlists'),
    path('buy-votes/', views.buy_votes, name='buy_votes'),
    path('buy-votes/success/', views.buy_votes_success, name='buy_votes_success'),
    path('stripe/webhook/', stripe_webhook, name='stripe_webhook'),


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
