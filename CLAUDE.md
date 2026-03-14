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
- **Party**: Events with associated playlists, voting limits (`max_votes_per_user`), unique join codes, song request cost (`request_cost`)
- **Playlist**: Spotify playlists linked to parties (one-to-one via Party.playlist)
- **Song**: Tracks from playlists with metadata (BPM, Camelot key), vote counts, played status
- **Vote**: Many-to-many relationship tracking user votes per song per party
- **VotePackage**: Records of purchased vote credits via Stripe
- **SongRequest**: User requests for songs not in playlist (status: pending/accepted/rejected, includes coins_cost)
- **Notification**: System notifications for users (type: song_accepted/song_played/coins_purchased/coins_received, with is_read flag)

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

**Audio Features Fallback Chain:**
When BPM or key data is missing, the system tries multiple sources in order:
1. **Spotify Audio Features API** (primary source) - Most reliable and complete
2. **GetSongBPM API** (secondary) - Specialized music metadata service with aggressive fuzzy matching (8 search strategies)
3. **MusicBrainz** (tertiary) - Community-driven database, searches user-contributed tags for BPM/key data

This cascading approach maximizes metadata coverage across different music catalogs.

### Coins and Vote System (jukebox/votes.py)

The application uses a dual-currency system:

**Coins (Global Currency):**
- Users purchase Coins via Stripe at `/buy-coins/`
- Coins persist globally across all parties
- Used for: converting to votes, requesting songs
- Stored in `User.credits` field

**Votes (Party-Specific):**
- Each party has `max_votes_per_user` base limit
- Users convert Coins to Votes with bonus tiers (e.g., 5 Coins → 11 Votes)
- `get_user_votes_left()` calculates: base + purchased - used votes
- Each vote on a song consumes 1 vote from party-specific pool
- Cannot vote if party votes exhausted (must convert more Coins)

**Conversion Rates (with bonuses):**
- 1 Coin → 2 Votes
- 2 Coins → 4 Votes
- 3 Coins → 6 Votes
- 5 Coins → 11 Votes (+1 bonus)
- 10 Coins → 25 Votes (+5 bonus)
- 20 Coins → 60 Votes (+20 bonus)

### Payment Flow

1. User initiates purchase at `/buy-coins/`
2. Stripe Checkout session created with party/coins metadata
3. On success, Stripe webhook (`/stripe/webhook/`) adds coins to `User.credits`
4. Coins are global; votes are party-specific (determined by max_votes_per_user + VotePackage converted from coins)

### Forms with Dynamic Spotify Data (jukebox/forms.py)

`PartySettingsForm` dynamically loads Spotify playlists:
- On form initialization, fetches user's playlists if no playlist currently assigned
- On save, creates/links `Playlist` object and imports all tracks as `Song` objects
- Retrieves BPM and Camelot key for each track via Spotify audio features API

### Notification System (jukebox/notifications.py)

The application features a complete notification system that alerts users about important events:

**Data Model:**
- `Notification` model with fields: user, type, title, message, song, song_request, amount, is_read, created_at
- Type choices: `song_accepted`, `song_played`, `coins_purchased`, `coins_received`

**Notification Creation:**
- `create_song_accepted_notification()`: When DJ accepts a song request
- `create_song_played_notification()`: When a voted song is played (notifies all voters)
- `create_coins_purchased_notification()`: When user purchases coins via Stripe
- `create_coins_received_notification()`: When user receives coins (gifts, promos)

**UI Integration:**
- Bell icon in TopBar shows unread notification count in red badge
- Clicking bell navigates to `/notifications/` page (not a dropdown)
- Visiting notifications page auto-marks all as read
- Context processor `jukebox.context_processors.unread_notifications_count` provides global count

**User Experience:**
- No browser `alert()` popups anywhere in the application
- Bootstrap dismissible alerts display in-page messages
- Messages auto-hide after 5 seconds with smooth fade
- Auto-scroll to top when message appears
- Pages reload after AJAX operations to update badge counts

### Song Request System

Users can request songs not in the party playlist:
- Search Spotify tracks via `/songs/request/`
- Requests cost coins (configurable per party via `request_cost` field)
- DJ reviews requests at `/dj/manage-requests/`
- On acceptance: coins charged, song added to party, user notified
- On rejection: no charge, user can re-request different song
- `SongRequest` model tracks: user, party, song details, status (pending/accepted/rejected), coins_cost

### Authentication

- Uses django-allauth with Spotify social auth provider
- Email verification is mandatory (`ACCOUNT_EMAIL_VERIFICATION = "mandatory"`)
- Spotify scopes: user-read-email, user-read-private, playlist-read-private, playlist-read-collaborative
- Login redirects handled via `LOGIN_REDIRECT_URL` and `ACCOUNT_SIGNUP_REDIRECT_URL`

## Key URL Patterns

- `/` - Main entry (redirects to party selection if no party in session)
- `/select-party/` - Choose active party
- `/songs/` - Song list for selected party (voting interface)
- `/songs/swipe/` - Busca Match voting interface (swipe like/next)
- `/songs/request/` - Request new songs via Spotify search
- `/notifications/` - View all notifications (auto-marks as read)
- `/party/<id>/settings/` - Party configuration (DJ/admin only)
- `/dj/` - DJ backoffice (superuser only)
- `/dj/dashboard/` - DJ dashboard with song stats (superuser only)
- `/dj/manage-requests/` - Manage song requests (superuser only)
- `/buy-coins/` - Purchase coins (virtual currency)
- `/stripe/webhook/` - Stripe webhook endpoint (CSRF exempt)
- `/accounts/` - django-allauth auth URLs
- `/admin/` - Django admin site

## DJ/Superuser Features

- Create parties via `/dj/` backoffice
- Link Spotify playlists to parties in party settings
- View all songs with vote counts and BPM/key metadata
- Mark songs as played via dashboard (triggers notifications to voters)
- Manage song requests at `/dj/manage-requests/`:
  - Accept requests: charges user coins, adds song to party, creates notification
  - Reject requests: no charge, user can request another song
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
- **No browser alert() popups**: All user feedback uses Bootstrap dismissible alerts that auto-hide
- **Real-time updates**: AJAX operations reload pages to update notification badges and UI state
- Context processors provide global template variables: `selected_party`, `user_avatar_url`, `unread_notifications_count`
