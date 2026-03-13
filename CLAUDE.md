# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DJ Jukebox is a Django web application that allows DJs to create party events where attendees can vote on songs from Spotify playlists. Users authenticate via django-allauth (including Spotify OAuth), purchase vote credits via Stripe, and vote on songs during events.

## Development Setup

### Running the Development Server
```bash
python manage.py runserver
```

### Database Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### Create Superuser (for DJ backoffice access)
```bash
python manage.py createsuperuser
```

### Running Tests
```bash
python manage.py test jukebox
```

### Accessing Django Shell
```bash
python manage.py shell
```

## Environment Variables

The project uses python-dotenv to load environment variables from a `.env` file. Required variables:

- `STRIPE_PUBLIC_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` - Stripe payment integration
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` - Spotify API credentials
- `GMAIL_USER`, `GMAIL_APP_PASSWORD` - Email sending for account verification

## Architecture

### Data Model Relationships

- **User** (custom AbstractUser): Has `credits` field for purchased votes
- **Party**: Events with associated playlists, voting limits (`max_votes_per_user`), unique join codes
- **Playlist**: Spotify playlists linked to parties (one-to-one via Party.playlist)
- **Song**: Tracks from playlists with metadata (BPM, Camelot key), vote counts, played status
- **Vote**: Many-to-many relationship tracking user votes per song per party
- **VotePackage**: Records of purchased vote credits via Stripe

### Session-Based Party Selection

The application uses Django sessions to track which party a user is currently viewing:
- `request.session['selected_party_id']` stores the active party
- Users select a party via `/select-party/` before accessing song lists
- Context processor `jukebox.context_processors.selected_party` makes `selected_party` available in all templates

### Spotify Integration (jukebox/spotify_api.py)

- Retrieves user OAuth tokens via `allauth.socialaccount.models.SocialToken`
- `get_user_playlists()`: Fetches user's Spotify playlists
- `get_playlist_tracks()`: Retrieves tracks with audio features (BPM, key)
- Converts Spotify key/mode to Camelot notation (e.g., "8B", "5A") for DJ harmonic mixing
- Chunks audio feature requests (50 tracks per call) to handle API limits

### Vote Credit System (jukebox/votes.py)

- Users have global `credits` that persist across parties
- Each party has `max_votes_per_user` base limit
- Additional votes can be purchased via Stripe (`VotePackage`)
- `get_user_votes_left()` calculates: base + purchased - used votes
- Voting requires both party-specific votes remaining AND global credits > 0
- Each vote consumes 1 credit

### Payment Flow

1. User initiates purchase at `/buy-votes/`
2. Stripe Checkout session created with party/vote metadata
3. On success, Stripe webhook (`/stripe/webhook/`) adds credits to `User.credits`
4. Credits are global; votes are party-specific (determined by max_votes_per_user + VotePackage)

### Forms with Dynamic Spotify Data (jukebox/forms.py)

`PartySettingsForm` dynamically loads Spotify playlists:
- On form initialization, fetches user's playlists if no playlist currently assigned
- On save, creates/links `Playlist` object and imports all tracks as `Song` objects
- Retrieves BPM and Camelot key for each track via Spotify audio features API

### Authentication

- Uses django-allauth with Spotify social auth provider
- Email verification is mandatory (`ACCOUNT_EMAIL_VERIFICATION = "mandatory"`)
- Spotify scopes: user-read-email, user-read-private, playlist-read-private, playlist-read-collaborative
- Login redirects handled via `LOGIN_REDIRECT_URL` and `ACCOUNT_SIGNUP_REDIRECT_URL`

## Key URL Patterns

- `/` - Main entry (redirects to party selection if no party in session)
- `/select-party/` - Choose active party
- `/songs/` - Song list for selected party (voting interface)
- `/party/<id>/settings/` - Party configuration (DJ/admin only)
- `/dj/` - DJ backoffice (superuser only)
- `/dj/dashboard/` - DJ dashboard with song stats (superuser only)
- `/buy-votes/` - Purchase vote credits
- `/stripe/webhook/` - Stripe webhook endpoint (CSRF exempt)
- `/accounts/` - django-allauth auth URLs
- `/admin/` - Django admin site

## DJ/Superuser Features

- Create parties via `/dj/` backoffice
- Link Spotify playlists to parties in party settings
- View all songs with vote counts and BPM/key metadata
- Mark songs as played via dashboard
- Access requires `@user_passes_test(lambda u: u.is_superuser)`

## Database

- SQLite (`db.sqlite3`) in development
- Custom user model: `AUTH_USER_MODEL = 'jukebox.User'`

## Static Files

- Static files located in `jukebox/static/`
- Includes FontAwesome vendor files
- `STATIC_URL = '/static/'`

## Notes

- The `acousticbrainz_api.py` module exists but is not actively used (AcousticBrainz service is deprecated)
- Current implementation uses Spotify's audio features API for BPM and key detection
- Templates use bootstrap-based admin theme (SB Admin 2)
- Logging is configured to DEBUG level in development
