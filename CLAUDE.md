# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

DJ Jukebox is a Django web application where DJs create party events and attendees vote on songs from Spotify playlists. Users authenticate via Spotify OAuth, purchase vote credits via Stripe, and vote/request songs during events.

**Domains:**
- `djukebox.click` — Static landing pages (`landing/`)
- `app.djukebox.click` — Django app

## Development Setup

```bash
python manage.py runserver       # Dev server
python manage.py makemigrations  # After model changes
python manage.py migrate
python manage.py createsuperuser # DJ backoffice access
python manage.py test jukebox    # Run tests
python manage.py shell
```

## Environment Variables (`.env`)

- `STRIPE_PUBLIC_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`
- `GMAIL_USER`, `GMAIL_APP_PASSWORD`

## Architecture

### Data Models

- **User** (custom AbstractUser): `credits` field stores global Coins
- **Party**: `max_votes_per_user`, `request_cost`, unique join code, optional cover image, location radius
- **Playlist**: one-to-one with Party, linked Spotify playlist
- **Song**: title, artist, BPM, Camelot key, vote count, played status
- **Vote**: user × song × party (many-to-many)
- **VotePackage**: records of coin→vote conversions per party
- **SongRequest**: status `pending/accepted/rejected`, `coins_cost`
- **Notification**: types `song_accepted/song_played/coins_purchased/coins_received`, `is_read`

### Session-Based Party Selection

`request.session['selected_party_id']` — set via `/select-party/`, made available globally via `jukebox.context_processors.selected_party`.

### Coins & Votes (`jukebox/votes.py`)

Two-currency system:
- **Coins** (`User.credits`): global, purchased via Stripe, used to convert to votes or request songs
- **Votes**: party-specific = `max_votes_per_user` base + VotePackage purchased votes − used votes

Conversion rates (coins → votes): 1→2, 2→4, 3→6, 5→11, 10→25, 20→60

### Spotify Integration (`jukebox/spotify_api.py`)

OAuth tokens via `allauth.socialaccount.models.SocialToken`. BPM/key fallback chain:
1. Spotify Audio Features API (primary)
2. SongBPM scrape (secondary)
3. SongData scrape (tertiary)
4. MusicBrainz (final fallback)

### Notifications (`jukebox/notifications.py`)

Bell icon in TopBar with unread badge. Navigates to `/notifications/` (not a dropdown). Visiting auto-marks all as read. Count provided globally via `jukebox.context_processors.unread_notifications_count`.

### Payment Flow

`/buy-coins/` → Stripe Checkout → webhook at `/stripe/webhook/` (CSRF exempt) → adds coins to `User.credits`.

### Song Requests

`/songs/request/` → Spotify search → costs coins → DJ reviews at `/dj/manage-requests/` → accept (charge + add song + notify) or reject (no charge).

### Authentication

django-allauth with Spotify OAuth. Email verification mandatory. Spotify scopes: `user-read-email`, `user-read-private`, `playlist-read-private`, `playlist-read-collaborative`.

## Internationalisation (i18n)

- Default language: **Català** (`ca`), also English (`en`)
- URLs prefixed: `/ca/...` and `/en/...` (via `i18n_patterns`, `prefix_default_language=True`)
- Language stored in cookie `django_language` (1 year expiry)
- Translation files: `locale/ca|en/LC_MESSAGES/django.po` and `jukebox/locale/ca|en/`
- Templates use `{% load i18n %}` + `{% trans %}` / `{% blocktrans %}`

## Static Files

- Served by **WhiteNoise** (`CompressedManifestStaticFilesStorage`) — gzip/brotli + content-hash
- CSS files in `jukebox/static/jukebox/css/`:
  - `base.css` — shared admin/app styles (extracted from admin_base.html)
  - `song_list.css`, `song_swipe.css`, `select_party.css`, `dj_dashboard.css` — page-specific
  - `app.css` — global app overrides

## Key URL Patterns

- `/<lang>/` — party selection (main entry)
- `/<lang>/select-party/` — choose active party
- `/<lang>/songs/` — song list + voting interface
- `/<lang>/songs/swipe/` — Busca Match swipe interface
- `/<lang>/songs/request/` — request songs via Spotify search
- `/<lang>/notifications/` — notifications (auto-marks read)
- `/<lang>/party/<id>/settings/` — party config (DJ only)
- `/<lang>/dj/` — DJ backoffice (superuser only)
- `/<lang>/dj/dashboard/` — song stats + mark played
- `/<lang>/dj/manage-requests/` — manage song requests
- `/<lang>/buy-coins/` — purchase coins
- `/stripe/webhook/` — Stripe webhook (no lang prefix, CSRF exempt)
- `/accounts/` — django-allauth
- `/admin/` — Django admin

## Frontend Design System

The app uses a **custom "Sonic" design system** built on Bootstrap 4:
- `admin_base.html` is the base template for all app pages
- TopBar, BottomBar (mobile), sidebar navigation
- No `alert()` popups — Bootstrap dismissible alerts, auto-hide 5 s with fade
- AJAX operations reload the page to keep badge counts fresh

**Landing pages** (`landing/`) use **Tailwind CSS** (CDN) with Epilogue + Plus Jakarta Sans fonts. Separate from the Django app — pure static HTML.

## DJ/Superuser Features

Access gated by `@user_passes_test(lambda u: u.is_superuser)`:
- Create parties, link Spotify playlists, import songs with BPM/Camelot key
- Dashboard: view vote counts, mark songs as played (notifies all voters)
- Manage song requests: accept (charge coins, add song, notify) or reject

## Context Processors

All templates receive: `selected_party`, `user_avatar_url`, `unread_notifications_count`

## Database

SQLite (`db.sqlite3`) in development. `AUTH_USER_MODEL = 'jukebox.User'`

## Notes

- `acousticbrainz_api.py` exists but is unused (service deprecated)
- `design/` folder contains reference designs (Stitch exports) — not served
- `docs/archive/` contains old plan and setup documents
