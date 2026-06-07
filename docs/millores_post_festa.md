# Millores post-festa — Gínjols 30 Anys (23 maig 2026)

> Anàlisi basada en `server.log` (172k línies) i la BD de producció.  
> 4,990 requests · 46 usuaris · 1,498 vots · 127 cançons · **0 errors 500 funcionals**

---

## Evidències recollides

### Tràfic i rendiment

| Indicador | Valor |
|---|---|
| Requests totals (23 maig) | 4,990 |
| Pic absolut | 21:34 — **277 req/min**, 19 req/s |
| Rampa d'entrada | 45 req (21:30) → 277 req (21:34) en 4 minuts |
| Dispositius mòbil / desktop | **93% mòbil** (4,645 vs 345 req) |
| Mida `/ca/songs/` | avg **922 KB**, max **1,135 KB** |
| Mida `/ca/songs/swipe/` | avg **551 KB**, max **686 KB** |
| Usuaris que van haver de fer login | **142** (redirect `?next=/ca/songs/`) |
| Comptes nous creats durant la festa | 14 |
| Requests de login/signup/google al pic | 240 (en 5 minuts) |

**Causa del "petó"**: HTML de ~1 MB servit per Gunicorn sense compressió. Django té `GZipMiddleware` disponible però no activat. WhiteNoise comprimeix estàtics però no les respostes de views. A 19 req/s, Gunicorn estava saturant workers.

---

### Errors en producció (confirmats a `server.log` amb path `/home/ubuntu/app/venv/python3.13`)

#### E1 · 500 — `TemplateSyntaxError` a `/accounts/password/reset/done/`
- **Quan**: 21:35:17, durant el pic
- **Afectació**: 1 persona (Android Chrome) intentant recuperar contrasenya
- **Causa**: Template d'allauth usa `{% url ''account_login'' %}` amb cometes dobles dins les simples — `TemplateSyntaxError: Could not parse the remainder: ''account_login'' from ''account_login''`
- **Fix**: Override del template `account/password_reset_done.html` amb la sintaxi correcta: `{% url 'account_login' %}`

#### E2 · Spotify token refresh continu (105 ocurrències)
- **Usuari afectat**: usuari id=6 (probablement el DJ / compte admin)
- **Seqüència**: "Spotify app credentials are missing" → "400 Bad Request" en refresc → "Unable to refresh Spotify token"
- **Causa probable**: el SocialToken de l'usuari 6 ha caducat i no es pot refrescar (refresh token invàlid o revocat). Cada vegada que el `status-api` intenta comprovar coses, reintenta el token.
- **Fix**: reconnectar el compte Spotify de l'usuari 6 des de l'admin. Afegir gestió de `SocialToken.DoesNotExist` i expiració per no reintentar cada request.

#### E3 · Spotify Audio Features API → 403 sistemàtic
- **Context**: al importar cançons a noves parties (party 2, analyze-song)
- **Causa**: Spotify ha restringit `/v1/audio-features/` per a apps en mode Development des de novembre 2024
- **Impacte**: BPM i clau Camelot no s'obtenen via Spotify; el sistema cau al fallback yt-dlp que també falla (veure E4)
- **Fix**: Eliminar Spotify Audio Features de la cadena i passar directament a SongBPM scrape + MusicBrainz. O migrar a Spotify `/v1/recommendations` + anàlisi local.

#### E4 · yt-dlp falla en tots els intents (~25s de timeout)
- **Error**: `[youtube] ...: Requested format is not available. Use --list-formats`
- **Causa**: YouTube ha canviat els formats disponibles (likely `bestaudio` ja no funciona sense autenticació). yt-dlp probablement desactualitzat.
- **Impacte**: cada analyze-song triga 25s i falla → 500 a `/ca/party/2/analyze-song/`
- **Fix**: `pip install -U yt-dlp` al servidor. Canviar el format a `worstaudio` o `m4a/bestaudio[ext=m4a]`. Considerar eliminar yt-dlp si Spotify 403 ja fa inútil el BPM analysis.

---

### Errors en entorn local (path `/Users/djkram/.venv/python3.12`) — no afecten producció però cal resoldre

#### L1 · `MultipleObjectsReturned` a allauth — `/accounts/login/` i `/ca/profile/` (12 ocurrències)
- **Causa**: `allauth.socialaccount.adapter.get_app()` troba múltiples registres `SocialApp` per al provider `spotify` a la BD local
- **Fix**: `python manage.py shell` → `from allauth.socialaccount.models import SocialApp; SocialApp.objects.filter(provider='spotify')` → esborrar els duplicats. Mantenir-ne un de sol.

#### L2 · `TemplateSyntaxError` a `party_settings.html` (línia 3464)
- **Error**: `Invalid block tag 'endblock', expected 'elif', 'else' or 'endif'`
- **Causa**: un `{% endblock %}` apareix dins d'un bloc `{% if %}` que no està tancat
- **Fix**: revisar el template `jukebox/templates/jukebox/party_settings.html` al voltant de la línia 3464

---

### Observació d'ús — el DJ no va marcar cançons com a reproduïdes

- **Dada**: `played=False` per a les 127 cançons — cap marcada durant la festa
- **Implicació**: les notificacions de "cançó reproduïda" no van sortir, i la llista no es va ordenar per `played`
- **Causa probable**: la funcionalitat no era còmode d'usar des del mòbil en directe, o el DJ no la coneixia

---

## Pla de millores prioritzat

### P1 · Rendiment primera càrrega (CRÍTIC per a properes festes)

**Problema**: ~1 MB de HTML per request sense compressió → Gunicorn saturat al pic.

**Accions**:
1. Activar `django.middleware.gzip.GZipMiddleware` a `MIDDLEWARE` (el primer, abans de `SecurityMiddleware`) — reducció estimada ~85% (1 MB → ~150 KB)
2. Paginació de la llista de cançons (`/ca/songs/`): carregar les primeres 30-50 per AJAX, lazy load en scroll. La playlist de 127 cançons és manejable però creixerà.
3. Afegir `nginx` davant de Gunicorn per servir estàtics, gestionar gzip i TLS (actualment Gunicorn serveix directament)

**Impacte esperat**: primera càrrega <3s en 4G amb 50 usuaris concurrents (ara era >10s)

---

### P2 · Eliminar fricció del login (IMPORTANT per UX)

**Problema**: 142 usuaris van haver d'autenticar-se abans d'entrar, 14 van crear compte nou. Flux: QR → login → confirm email → songs = 3-4 passos.

**Accions**:
1. Considerar accés anònim/guest per a convidats: link únic de party que entra directament sense compte
2. O simplificar: login amb Google/Spotify en un sol clic visible (ara és formulari email/password per defecte)
3. Eliminar la verificació d'email obligatòria per a convidats — `ACCOUNT_EMAIL_VERIFICATION = 'optional'` per al flux de party join

---

### P3 · Marcar cançons en directe (MILLORA DJ UX)

**Problema**: el DJ no va marcar cap cançó com a reproduïda — les notificacions no van funcionar.

**Accions**:
1. Afegir un botó prominent "Ara sona ▶" al dashboard del DJ, visible sense scroll
2. Considerar un mode "DJ live" simplificat: pantalla mínima amb les top-5 i un botó gran per marcar
3. Notificació visual als usuaris quan una cançó que han votat comença a sonar

---

### P4 · Fix errors confirmats

| # | Error | Acció |
|---|---|---|
| E1 | 500 `password/reset/done/` | Override template allauth amb sintaxi correcta |
| E2 | Spotify token usuari 6 | Reconnectar des d'admin + millorar gestió d'expiració |
| E3 | Spotify Audio Features 403 | Eliminar de la cadena, usar SongBPM + MusicBrainz |
| E4 | yt-dlp `format not available` | `pip install -U yt-dlp` + canviar selector de format |
| L1 | MultipleObjectsReturned allauth local | Esborrar SocialApp duplicats a BD local |
| L2 | TemplateSyntaxError party_settings | Revisar `party_settings.html` línia ~3464 |

---

### P5 · Monitoratge (per a properes festes)

**Problema**: no hi havia alertes en temps real durant la festa.

**Accions**:
1. Afegir temps de resposta als logs de Gunicorn (`--access-logformat` amb `%(L)s`)
2. Script de monitoratge simple que alerta si hi ha errors 500 o si la latència puja
3. Considerar Sentry free tier per a captura automàtica d'excepcions

---

## Resum de mètriques de la festa

```
Party:          Gínjols 30 Anys
Data:           23 maig 2026, 21:30–23:00
Usuaris actius: 37 / 46 registrats
Vots emesos:    1,498 / 2,590 possibles (màx 70/usuari × 37 actius)
Participació:   80% dels usuaris van usar >5 vots
Cançons votades: 127 / 127 (100% de la playlist)
Top 3:          Sweet Caroline (21v), Fireball (19v), SUPERESTRELLA (18v)
Errors 500:     1 (password reset, no crític)
Errors funcionals: 0
```
