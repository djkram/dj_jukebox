window.slPreviewActive = false;
window.slPreviewTitle  = '';
window.slPreviewArtist = '';

window.updateLcdForPreview = function(title, artist, isPlaying) {
  var lcd        = document.getElementById('slLcd1');
  var btn        = document.getElementById('slPreviewPlayBtn');
  var st         = document.getElementById('slStatus1');
  var detail     = document.getElementById('slDetail1');
  var songBlock  = document.getElementById('slPreviewSongBlock');
  var songTitle  = document.getElementById('slPreviewTitle');
  var songArtist = document.getElementById('slPreviewArtist');
  var ticker     = document.getElementById('slPreviewTicker');
  var tickerInner= document.getElementById('slPreviewTickerInner');
  // Mobile LCD elements (sl-lcd style)
  var mLcd        = document.getElementById('slMobileLcd');
  var mStatusText = document.getElementById('slMobileStatus1');
  var mNextStep   = document.getElementById('slMobileDetail1');

  var mSongBlock  = document.getElementById('slMobileNpBlock');
  var mTicker     = document.getElementById('slMobileNpTicker');
  var mTickerInner= document.getElementById('slMobileNpTickerInner');
  var mBtns       = document.getElementById('slMobPreviewBtns');
  var mIcon       = document.getElementById('slMobPreviewIcon');

  function setMobTickerText(text) {
    if (!mTickerInner || !mTicker) return;
    mTickerInner.innerHTML = '';
    var sp = document.createElement('span');
    sp.className = 'sl-lcd-np-title';
    sp.textContent = text;
    mTickerInner.appendChild(sp);
    mTickerInner.classList.remove('is-scrolling');
    mTickerInner.style.removeProperty('--sl-scroll-px');
    requestAnimationFrame(function() {
      var ov = mTickerInner.scrollWidth - mTicker.offsetWidth;
      if (ov > 6) {
        mTickerInner.style.setProperty('--sl-scroll-px', '-' + ov + 'px');
        mTickerInner.classList.add('is-scrolling');
      }
    });
  }

  if (title) {
    window.slPreviewActive = true;
    window.slPreviewTitle  = title;
    window.slPreviewArtist = artist || '';

    // Desktop LCD
    if (isPlaying) {
      if (st)     st.textContent     = '▶ PREESCOLTANT';
      if (detail) detail.textContent = artist || '';
      if (lcd)    lcd.classList.add('is-previewing');
    } else {
      if (st)     st.textContent     = '⏸ PREESCOLTA PAUSADA';
      if (detail) detail.textContent = artist || '';
      if (lcd)    lcd.classList.remove('is-previewing');
    }
    if (songTitle)  songTitle.textContent  = title;
    if (songArtist) songArtist.textContent = artist || '';
    if (songBlock)  songBlock.style.display = '';
    if (btn) btn.classList.toggle('is-pressed', isPlaying);
    if (ticker && tickerInner) {
      tickerInner.classList.remove('is-scrolling');
      tickerInner.style.removeProperty('--sl-scroll-px');
      requestAnimationFrame(function() {
        var ov = tickerInner.scrollWidth - ticker.offsetWidth;
        if (ov > 6) {
          tickerInner.style.setProperty('--sl-scroll-px', '-' + ov + 'px');
          tickerInner.classList.add('is-scrolling');
        }
      });
    }

    // Mobile LCD — song section only
    if (mSongBlock) mSongBlock.style.display = '';
    if (mBtns)      mBtns.style.display = '';
    if (mIcon)      mIcon.textContent = isPlaying ? 'pause' : 'play_arrow';
    if (isPlaying) {
      if (mLcd) mLcd.classList.add('is-previewing');
    } else {
      if (mLcd) mLcd.classList.remove('is-previewing');
    }

    window._mobPreviewData = { title: title, artist: artist || '' };
    if (window._mobPreviewInterval) clearInterval(window._mobPreviewInterval);
    var label = isPlaying ? '▶ PREESCOLTANT' : '⏸ PREESCOLTA PAUSADA';
    window._mobPreviewAlt = true;
    setMobTickerText(label);
    window._mobPreviewInterval = setInterval(function() {
      window._mobPreviewAlt = !window._mobPreviewAlt;
      var d = window._mobPreviewData;
      if (window._mobPreviewAlt) {
        setMobTickerText(label);
      } else {
        setMobTickerText(d.title + '  ·  ' + d.artist);
      }
    }, 3000);

  } else {
    window.slPreviewActive = false;
    if (songBlock) songBlock.style.display = 'none';
    if (tickerInner) { tickerInner.classList.remove('is-scrolling'); tickerInner.style.removeProperty('--sl-scroll-px'); }
    if (lcd) lcd.classList.remove('is-previewing');
    if (btn) btn.classList.remove('is-pressed');
    if (mLcd) mLcd.classList.remove('is-previewing');
    if (window._mobPreviewInterval) { clearInterval(window._mobPreviewInterval); window._mobPreviewInterval = null; }
    if (mSongBlock) mSongBlock.style.display = 'none';
    if (mBtns)      mBtns.style.display = 'none';
    if (mTickerInner) { mTickerInner.classList.remove('is-scrolling'); mTickerInner.style.removeProperty('--sl-scroll-px'); }
    if (window.slRestoreMobileLcd) window.slRestoreMobileLcd();
    if (window.slRestoreLcd) window.slRestoreLcd();
  }
};

// Function to show dismissible alerts
function showSpotifyAlert(message, type = 'warning') {
  const alertArea = document.getElementById('spotify-alert-area');
  if (!alertArea) return;

  const alertId = 'alert-' + Date.now();
  const iconClass = type === 'danger' ? 'fa-exclamation-triangle' : type === 'info' ? 'fa-info-circle' : 'fa-exclamation-circle';

  alertArea.innerHTML = `
    <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show shadow" role="alert">
      <i class="fas ${iconClass} me-2"></i>
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>
  `;

  window.scrollTo({ top: 0, behavior: 'smooth' });

  setTimeout(() => {
    const alert = document.getElementById(alertId);
    if (alert) {
      alert.classList.remove('show');
      setTimeout(() => alertArea.innerHTML = '', 150);
    }
  }, 5000);
}

// Spotify Web Playback SDK Variables
let spotifyPlayer = null;
let spotifyDeviceId = null;
let currentPlayingSpotifyId = null;
let isCurrentlyPlaying = false;
let SPOTIFY_TOKEN = null;
let spotifySdkReady = false;
let spotifyPlayerInitPromise = null;

window.onSpotifyWebPlaybackSDKReady = () => {
  spotifySdkReady = true;
};

function updateSpotifyButtons(track_id, isPlaying) {
  document.querySelectorAll('.spotify-play-btn').forEach(btn => {
    const btnSpotifyId = btn.dataset.spotifyId;
    const icon = btn.querySelector('i, span.material-symbols-outlined');
    const overlay = btn.closest('.play-overlay');

    if (btnSpotifyId === track_id) {
      if (isPlaying) {
        if (icon.classList.contains('material-symbols-outlined')) {
          icon.textContent = 'pause';
        } else {
          icon.classList.remove('fa-play');
          icon.classList.add('fa-pause');
        }
      } else {
        if (icon.classList.contains('material-symbols-outlined')) {
          icon.textContent = 'play_arrow';
        } else {
          icon.classList.remove('fa-pause');
          icon.classList.add('fa-play');
        }
      }
      if (overlay) overlay.classList.add('is-playing');
    } else {
      if (icon.classList.contains('material-symbols-outlined')) {
        icon.textContent = 'play_arrow';
      } else {
        icon.classList.remove('fa-pause');
        icon.classList.add('fa-play');
      }
      if (overlay) overlay.classList.remove('is-playing');
    }
  });
}

function ensureSpotifyPlayer() {
  if (spotifyPlayer && spotifyDeviceId) {
    return Promise.resolve(spotifyPlayer);
  }

  if (!spotifySdkReady || !window.Spotify) {
    showSpotifyAlert(window.JukeboxConfig.i18n.spotifyNotReady, 'info');
    return Promise.reject(new Error('Spotify SDK not ready'));
  }

  if (spotifyPlayerInitPromise) {
    return spotifyPlayerInitPromise;
  }

  spotifyPlayerInitPromise = new Promise((resolve, reject) => {
    spotifyPlayer = new Spotify.Player({
      name: 'DJ Jukebox Web Player',
      getOAuthToken: cb => {
        fetch('/api/spotify-token/')
          .then(r => r.json())
          .then(data => { SPOTIFY_TOKEN = data.token; cb(data.token); })
          .catch(() => cb(null));
      },
      volume: 0.7
    });

    spotifyPlayer.addListener('ready', ({ device_id }) => {
      console.log('[SPOTIFY] Player ready with Device ID:', device_id);
      spotifyDeviceId = device_id;
      resolve(spotifyPlayer);
    });

    spotifyPlayer.addListener('not_ready', ({ device_id }) => {
      console.log('[SPOTIFY] Device ID has gone offline:', device_id);
    });

    spotifyPlayer.addListener('player_state_changed', state => {
      if (!state) {
        currentPlayingSpotifyId = null;
        isCurrentlyPlaying = false;
        updateSpotifyButtons(null, false);
        window.updateLcdForPreview(null, null, false);
        return;
      }
      if (window._spotifyStopped) return;

      const isPlaying = !state.paused;
      const track    = state.track_window.current_track;
      const track_id = track.id;

      currentPlayingSpotifyId = track_id;
      isCurrentlyPlaying = isPlaying;
      updateSpotifyButtons(track_id, isPlaying);
      window.updateLcdForPreview(track.name, track.artists[0].name, isPlaying);
    });

    spotifyPlayer.connect().then(success => {
      if (!success) {
        reject(new Error('Spotify player connection failed'));
      }
    }).catch(reject);
  }).catch(error => {
    spotifyPlayerInitPromise = null;
    throw error;
  });

  return spotifyPlayerInitPromise;
}

// Function to play a track using Spotify SDK
function playSpotifyTrack(spotifyId) {
  return ensureSpotifyPlayer().then(() => fetch(`https://api.spotify.com/v1/me/player/play?device_id=${spotifyDeviceId}`, {
    method: 'PUT',
    body: JSON.stringify({ uris: [`spotify:track:${spotifyId}`] }),
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${SPOTIFY_TOKEN}`
    },
  })).then(response => {
    if (response.ok) {
      console.log('[SPOTIFY] Playing track:', spotifyId);
    } else if (response.status === 403) {
      console.error('[SPOTIFY] Premium required');
      showSpotifyAlert(window.JukeboxConfig.i18n.spotifyPremiumRequired, 'warning');
    } else if (response.status === 401) {
      console.error('[SPOTIFY] Unauthorized');
      showSpotifyAlert(window.JukeboxConfig.i18n.spotifySessionExpired, 'danger');
    } else {
      console.error('[SPOTIFY] Error playing track:', response.status);
      showSpotifyAlert(window.JukeboxConfig.i18n.spotifyPlayError, 'danger');
    }
  });
}

// Setup play button and overlay listeners
document.addEventListener('DOMContentLoaded', function() {
  // CDJ preview play/pause button (desktop)
  var previewBtn = document.getElementById('slPreviewPlayBtn');
  if (previewBtn) {
    previewBtn.addEventListener('click', function() {
      if (!spotifyPlayer) return;
      if (isCurrentlyPlaying) {
        spotifyPlayer.pause().catch(function() {});
      } else {
        spotifyPlayer.resume().catch(function() {});
      }
    });
  }

  // Mobile preview play/pause button
  var mobPreviewBtn = document.getElementById('slMobPreviewBtn');
  if (mobPreviewBtn) {
    mobPreviewBtn.addEventListener('click', function() {
      if (!spotifyPlayer) return;
      if (isCurrentlyPlaying) {
        spotifyPlayer.pause().catch(function() {});
      } else {
        spotifyPlayer.resume().catch(function() {});
      }
    });
  }

  // Mobile stop button
  var mobStopBtn = document.getElementById('slMobStopBtn');
  if (mobStopBtn) {
    mobStopBtn.addEventListener('click', function() {
      if (!spotifyPlayer) return;
      window._spotifyStopped = true;
      spotifyPlayer.pause().catch(function() {});
      currentPlayingSpotifyId = null;
      isCurrentlyPlaying = false;
      updateSpotifyButtons(null, false);
      window.updateLcdForPreview(null, null, false);
    });
  }

  // Play button clicks
  document.querySelectorAll('.spotify-play-btn').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();

      const spotifyId = this.dataset.spotifyId;
      window._spotifyStopped = false;

      if (currentPlayingSpotifyId === spotifyId) {
        // Same track - toggle play/pause
        if (isCurrentlyPlaying) {
          // Currently playing, so pause
          console.log('[SPOTIFY] Pausing track');
          ensureSpotifyPlayer().then(() => spotifyPlayer.pause()).then(() => {
            console.log('[SPOTIFY] Paused successfully');
          }).catch(err => {
            console.error('[SPOTIFY] Error pausing:', err);
          });
        } else {
          // Currently paused, so resume
          console.log('[SPOTIFY] Resuming track');
          ensureSpotifyPlayer().then(() => spotifyPlayer.resume()).then(() => {
            console.log('[SPOTIFY] Resumed successfully');
          }).catch(err => {
            console.error('[SPOTIFY] Error resuming:', err);
          });
        }
      } else {
        // Different track - play it
        console.log('[SPOTIFY] Playing new track:', spotifyId);
        playSpotifyTrack(spotifyId);
      }
    });
  });

  // Overlay clicks
  document.querySelectorAll('.play-overlay').forEach(overlay => {
    overlay.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();

      const btn = this.querySelector('.spotify-play-btn');
      if (btn) {
        btn.click();
      }
    });
  });

  function cleanupSpotifyPlayback() {
    if (spotifyPlayer) {
      try {
        spotifyPlayer.pause();
      } catch (e) {
        console.warn('[SPOTIFY] Error pausing player during cleanup:', e);
      }
      try {
        spotifyPlayer.disconnect();
      } catch (e) {
        console.warn('[SPOTIFY] Error disconnecting player during cleanup:', e);
      }
    }
    spotifyPlayer = null;
    spotifyDeviceId = null;
    spotifyPlayerInitPromise = null;
    currentPlayingSpotifyId = null;
    isCurrentlyPlaying = false;
    updateSpotifyButtons(null, false);
    window.updateLcdForPreview(null, null, false);
  }

  window.addEventListener('pagehide', cleanupSpotifyPlayback);
  window.addEventListener('beforeunload', cleanupSpotifyPlayback);
  document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
      cleanupSpotifyPlayback();
    }
  });
});

document.addEventListener('DOMContentLoaded', function() {
  // Activar tooltips de Bootstrap
  var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });

  // Tabs mòbil per Maleta del DJ / El que ha sonat / Popers temes
  var mobileTabButtons = document.querySelectorAll('[data-mobile-tab]');
  var mobileTabBag = document.getElementById('mobile-tab-bag');
  var mobileTabPlayed = document.getElementById('mobile-tab-played');
  var mobileTabRecommended = document.getElementById('mobile-tab-recommended');
  var allMobileTabs = [mobileTabBag, mobileTabPlayed, mobileTabRecommended];

  mobileTabButtons.forEach(function(button) {
    button.addEventListener('click', function() {
      var target = button.getAttribute('data-mobile-tab');

      mobileTabButtons.forEach(function(btn) { btn.classList.remove('is-active'); });
      button.classList.add('is-active');

      allMobileTabs.forEach(function(tab) {
        if (tab) { tab.classList.add('d-none'); tab.classList.remove('d-flex'); }
      });

      var activeTab = null;
      if (target === 'played') activeTab = mobileTabPlayed;
      else if (target === 'recommended') activeTab = mobileTabRecommended;
      else activeTab = mobileTabBag;

      if (activeTab) { activeTab.classList.remove('d-none'); activeTab.classList.add('d-flex'); }
    });
  });

  // Filtrat de cançons desktop - Pending songs
  var searchPendingInput = document.getElementById('search-pending');
  if (searchPendingInput) {
    searchPendingInput.addEventListener('input', function() {
      var q = searchPendingInput.value.trim().toLowerCase();
      var rows = document.querySelectorAll('.pending-song-row');

      rows.forEach(function(row) {
        var title = (row.getAttribute('data-song-title') || '').toLowerCase();
        var artist = (row.getAttribute('data-song-artist') || '').toLowerCase();
        row.style.display = (title.includes(q) || artist.includes(q)) ? '' : 'none';
      });
    });
  }

  // Filtrat de cançons desktop - Played songs
  var searchPlayedInput = document.getElementById('search-played');
  if (searchPlayedInput) {
    searchPlayedInput.addEventListener('input', function() {
      var q = searchPlayedInput.value.trim().toLowerCase();
      var rows = document.querySelectorAll('.played-song-row');

      rows.forEach(function(row) {
        var title = (row.getAttribute('data-song-title') || '').toLowerCase();
        var artist = (row.getAttribute('data-song-artist') || '').toLowerCase();
        row.style.display = (title.includes(q) || artist.includes(q)) ? '' : 'none';
      });
    });
  }

  var mobileInput = document.getElementById('mobile-song-search');
  if (mobileInput) {
    var noResultsBox = document.getElementById('mobile-bag-no-results');
    var spotifySearchBtn = document.getElementById('mobile-bag-search-spotify-btn');

    mobileInput.addEventListener('input', function() {
      var q = mobileInput.value.trim().toLowerCase();
      var rawQuery = mobileInput.value.trim();
      var cards = document.querySelectorAll('.mobile-bag-song-card');
      var visibleCount = 0;

      cards.forEach(function(card) {
        var title = card.getAttribute('data-song-title').toLowerCase();
        var artist = card.getAttribute('data-song-artist').toLowerCase();
        var isMatch = (title.includes(q) || artist.includes(q));
        card.style.display = isMatch ? '' : 'none';
        if (isMatch) visibleCount += 1;
      });

      if (noResultsBox) {
        if (rawQuery && visibleCount === 0) {
          noResultsBox.classList.remove('d-none');
          if (spotifySearchBtn) {
            spotifySearchBtn.href = 'https://open.spotify.com/search/' + encodeURIComponent(rawQuery);
          }
        } else {
          noResultsBox.classList.add('d-none');
        }
      }
    });
  }
});

// ── LCD clocks ────────────────────────────────────────────────────────────
(function() {
  function hhMM() {
    var now = new Date();
    return String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');
  }
  function pad(n) { return String(n).padStart(2,'0'); }

  // Left clock: always HH:MM
  var el1 = document.getElementById('slClock1');
  function tickLeft() { if (el1) el1.textContent = hhMM(); }
  tickLeft();
  setInterval(tickLeft, 1000);

  // Right clock: chrono (elapsed since jukebox activated) when djjukebox_active, else HH:MM
  var el2 = document.getElementById('slClock2');
  var CHRONO_KEY = 'jukebox_chrono_' + window.JukeboxConfig.partyId;
  var IS_ACTIVE  = window.JukeboxConfig.partyStatus === 'djjukebox_active';

  if (IS_ACTIVE && el2) {
    var stored = localStorage.getItem(CHRONO_KEY);
    var startTs = stored ? parseInt(stored, 10) : Date.now();
    if (!stored) localStorage.setItem(CHRONO_KEY, startTs);

    el2.classList.add('is-chrono');
    function tickChrono() {
      var elapsed = Math.floor((Date.now() - startTs) / 1000);
      var h = Math.floor(elapsed / 3600);
      var m = Math.floor((elapsed % 3600) / 60);
      var s = elapsed % 60;
      el2.textContent = pad(h) + ':' + pad(m) + ':' + pad(s);
    }
    tickChrono();
    setInterval(tickChrono, 1000);
  } else {
    if (el2) el2.classList.remove('is-chrono');
    function tickRight() { if (el2) el2.textContent = hhMM(); }
    tickRight();
    setInterval(tickRight, 1000);
    if (!IS_ACTIVE) localStorage.removeItem(CHRONO_KEY);
  }
  // Mobile clock (HH:MM) + chrono when jukebox active
  var elMClock  = document.getElementById('slMobileClock');
  var elMClock2 = document.getElementById('slMobileClock2');
  function tickMobile() {
    var t = hhMM();
    if (elMClock)  elMClock.textContent = t;
    if (elMClock2) elMClock2.textContent = t;
  }
  tickMobile();
  setInterval(tickMobile, 1000);
})();

// ── Jukebox schedule countdown ────────────────────────────────────────────
(function() {
  var JB_START = window.JukeboxConfig.jukeboxStartsAt;
  var JB_END   = window.JukeboxConfig.jukeboxEndsAt;
  var IS_ACTIVE = window.JukeboxConfig.partyStatus === 'djjukebox_active';
  var IS_DONE   = window.JukeboxConfig.partyStatus === 'finished';

  function parseTime(str) {
    if (!str) return null;
    var p = str.split(':');
    var now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate(), parseInt(p[0],10), parseInt(p[1],10), 0);
  }

  function updateCountdown() {
    var text;
    if (IS_DONE) {
      text = 'sessió acabada';
    } else if (IS_ACTIVE) {
      var endT = parseTime(JB_END);
      if (endT) {
        var left = Math.floor((endT - Date.now()) / 60000);
        if (left > 0) { text = 'queden ' + left + ' min'; }
      }
      if (!text) text = 'en curs';
    } else {
      var startT = parseTime(JB_START);
      if (!startT) {
        text = 'horari no definit';
      } else {
        var diff = Math.floor((startT - Date.now()) / 60000);
        if (diff <= 0) { text = 'en breu'; }
        else { var h = Math.floor(diff / 60), m = diff % 60; text = 'falta ' + (h > 0 ? h + 'h ' : '') + m + ' min'; }
      }
    }
    ['slJbCountdown'].forEach(function(id) {
      var el = document.getElementById(id);
      if (el) el.textContent = text;
    });
  }

  updateCountdown();
  setInterval(updateCountdown, 30000);
})();

// ── Party status polling ───────────────────────────────────────────────────
(function() {
  var POLL_URL = window.JukeboxConfig.pollUrl;
  var currentStatus = window.JukeboxConfig.partyStatus;
  var partyDate = window.JukeboxConfig.partyDate;
  var initialNowPlaying = window.JukeboxConfig.nowPlaying.title;

  var LCD_STATE_CLASSES = ['sl-lcd-visible','sl-lcd-show','sl-lcd-requests','sl-lcd-active','sl-lcd-finished'];

  var STATUS_CLASS = {
    party_visible:    'sl-lcd-visible',
    show_party:       'sl-lcd-show',
    requests_open:    'sl-lcd-requests',
    djjukebox_active: 'sl-lcd-active',
    finished:         'sl-lcd-finished',
  };
  // ── Left LCD: voting & playlist state ─────────────────────────────────────
  // ── Left LCD: voting state ─────────────────────────────────────────────────
  var STATUS_LABEL = {
    party_visible:    'AVIAT',
    show_party:       'EXPLORA',
    requests_open:    'VOTA ARA',
    djjukebox_active: 'VOTA!',
    finished:         'ACABAT',
  };
  function detailText(status) {
    if (status === 'party_visible')    return 'La llista s\'obrirà aviat · espera';
    if (status === 'show_party')       return 'Vota els temes que vols sentir · jukebox no actiu';
    if (status === 'requests_open')    return 'Els vots s\'acumulen · espera l\'activació';
    if (status === 'djjukebox_active') return 'Com més vots té un tema, abans sona';
    if (status === 'finished')         return 'Gràcies per participar!';
    return '';
  }

  // ── Right LCD: jukebox mode state ─────────────────────────────────────────
  // ── Right LCD: jukebox mode state ─────────────────────────────────────────
  // ── Right LCD: jukebox mode state ─────────────────────────────────────────
  var RIGHT_STATUS_LABEL = {
    party_visible:    '○ STANDBY',
    show_party:       '● CUE',
    requests_open:    '● CUE',
    djjukebox_active: '▶ PLAY',
    finished:         '■ FI',
  };
  function rightDetailText(status) {
    if (status === 'djjukebox_active') return 'Sessió jukebox activa · el DJ segueix els vots';
    if (status === 'requests_open')    return 'Sessió pendent · els vots s\'acumulen';
    if (status === 'show_party')       return 'Sessió pendent · el DJ decidirà quan activar';
    if (status === 'party_visible')    return 'El DJ prepara la sessió';
    if (status === 'finished')         return 'Sessió tancada';
    return '—';
  }

  // Cache last known song data for LCD restore after preview
  var lastSongData = {
    nowPlaying:        initialNowPlaying || '',
    nowPlayingArtist:  window.JukeboxConfig.nowPlaying.artist,
    lastPlayed:        window.JukeboxConfig.lastPlayed.title,
    lastPlayedArtist:  window.JukeboxConfig.lastPlayed.artist,
    songsPlayed:       window.JukeboxConfig.songsPlayed,
  };

  // ── Status carousel: rota slides cada 5 s ──────────────────────────────
  function initCarousel(id) {
    var el = document.getElementById(id);
    if (!el) return;
    var slides = el.querySelectorAll('.sl-carousel-slide');
    if (slides.length < 2) return;
    var idx = 0;
    setInterval(function() {
      slides[idx].classList.remove('sl-slide-active');
      idx = (idx + 1) % slides.length;
      slides[idx].classList.add('sl-slide-active');
    }, 5000);
  }
  initCarousel('slCarousel1');
  initCarousel('slCarousel2');
  initCarousel('slMobileCarousel');

  // Mobile KPI + Times page alternation (synced)
  (function() {
    var kpiEl = document.getElementById('slMobKpiCarousel');
    var timEl = document.getElementById('slMobTimesCarousel');
    var kpiPages = kpiEl ? kpiEl.querySelectorAll('.mob-kpi-page') : [];
    var timPages = timEl ? timEl.querySelectorAll('.mob-times-page') : [];
    if (kpiPages.length < 2 && timPages.length < 2) return;
    var idx = 0;
    setInterval(function() {
      if (kpiPages.length > 1) {
        kpiPages[idx % kpiPages.length].classList.remove('mob-kpi-page-active');
      }
      if (timPages.length > 1) {
        timPages[idx % timPages.length].classList.remove('mob-times-page-active');
      }
      idx = (idx + 1);
      if (kpiPages.length > 1) {
        kpiPages[idx % kpiPages.length].classList.add('mob-kpi-page-active');
      }
      if (timPages.length > 1) {
        timPages[idx % timPages.length].classList.add('mob-times-page-active');
      }
    }, 5000);
  })();

  function updateKpiVisibility(status) {
    document.querySelectorAll('[data-kpi-states]').forEach(function(item) {
      var states = item.getAttribute('data-kpi-states').split(' ');
      item.style.display = states.indexOf(status) !== -1 ? '' : 'none';
    });
  }

  var MOBILE_STATUS_LABEL = {
    party_visible: 'AVIAT', show_party: 'EXPLORA',
    requests_open: 'VOTA ARA', djjukebox_active: 'VOTA!', finished: 'ACABAT',
  };
  var MOBILE_DETAIL = {
    party_visible: 'La llista obrirà aviat. Prepara\'t per votar els temes que vols sentir.',
    show_party: 'Explora la llista i vota els temes. El jukebox encara no és actiu, però els vots ja es comptabilitzen.',
    requests_open: 'Vota els temes que vols sentir! Els vots s\'acumulen a la cua. Quan el DJ activi el jukebox, sonaran els més votats.',
    djjukebox_active: 'El jukebox és actiu! Com més vots té un tema, abans sona. El DJ segueix la cua en directe.',
    finished: 'La sessió ha acabat. Gràcies per participar i votar!',
  };
  window.slRestoreMobileLcd = function() {
    var mst = document.getElementById('slMobileStatus1');
    var mns = document.getElementById('slMobileDetail1');
    if (mst) mst.textContent = MOBILE_STATUS_LABEL[currentStatus] || '';
    if (mns) mns.textContent = MOBILE_DETAIL[currentStatus] || '';
  };

  // Mobile now-playing: show/hide block + set text immediately
  function updateMobileNowPlaying(status) {
    if (window.slPreviewActive) return;
    var block  = document.getElementById('slMobileNpBlock');
    var ticker = document.getElementById('slMobileNpTicker');
    var inner  = document.getElementById('slMobileNpTickerInner');
    if (!block) return;
    if (status === 'djjukebox_active' && lastSongData.lastPlayed) {
      block.style.display = '';
      if (inner && ticker) {
        inner.innerHTML = '';
        var sp = document.createElement('span');
        sp.className = 'sl-lcd-np-title';
        sp.textContent = lastSongData.lastPlayed + '  ·  ' + (lastSongData.lastPlayedArtist || '');
        inner.appendChild(sp);
        inner.classList.remove('is-scrolling');
        inner.style.removeProperty('--sl-scroll-px');
        requestAnimationFrame(function() {
          var ov = inner.scrollWidth - ticker.offsetWidth;
          if (ov > 6) {
            inner.style.setProperty('--sl-scroll-px', '-' + ov + 'px');
            inner.classList.add('is-scrolling');
          }
        });
      }
    } else {
      block.style.display = 'none';
    }
  }

  // Standalone now-playing ticker alternation (decoupled from polling)
  (function() {
    var block  = document.getElementById('slMobileNpBlock');
    var ticker = document.getElementById('slMobileNpTicker');
    var inner  = document.getElementById('slMobileNpTickerInner');
    if (!block || !ticker || !inner) return;
    var ALT_TEXT = '▶ Sonant ara mateix a la sessió';
    var showSong = true;

    function setContent(text) {
      inner.innerHTML = '';
      var sp = document.createElement('span');
      sp.className = 'sl-lcd-np-title';
      sp.textContent = text;
      inner.appendChild(sp);
      inner.classList.remove('is-scrolling');
      inner.style.removeProperty('--sl-scroll-px');
      requestAnimationFrame(function() {
        var ov = inner.scrollWidth - ticker.offsetWidth;
        if (ov > 6) {
          inner.style.setProperty('--sl-scroll-px', '-' + ov + 'px');
          inner.classList.add('is-scrolling');
        }
      });
    }

    setInterval(function() {
      if (window.slPreviewActive) return;
      if (block.style.display === 'none') { showSong = true; return; }
      showSong = !showSong;
      if (showSong) {
        var song = lastSongData.lastPlayed;
        if (!song) return;
        setContent(song + '  ·  ' + (lastSongData.lastPlayedArtist || ''));
      } else {
        setContent(ALT_TEXT);
      }
    }, 4000);
  })();

  function applyStatus(status, nowPlaying, lastPlayed, songsPlayed) {
    // Desktop LCD color classes
    document.querySelectorAll('.sl-lcd').forEach(function(lcd) {
      LCD_STATE_CLASSES.forEach(function(c) { lcd.classList.remove(c); });
      if (STATUS_CLASS[status]) lcd.classList.add(STATUS_CLASS[status]);
    });

    // Right LCD wave: animate when jukebox active
    var lcd2 = document.getElementById('slLcd2');
    if (lcd2) {
      if (status === 'djjukebox_active') lcd2.classList.add('is-playing');
      else lcd2.classList.remove('is-playing');
    }

    // Mobile LCD wave + now-playing
    var mLcd = document.getElementById('slMobileLcd');
    if (mLcd) {
      if (status === 'djjukebox_active') mLcd.classList.add('is-playing');
      else mLcd.classList.remove('is-playing');
    }
    updateMobileNowPlaying(status);

    // Left LCD: voting info (skip if Spotify preview active)
    if (!window.slPreviewActive) {
      var st = document.getElementById('slStatus1');
      var dt = document.getElementById('slDetail1');
      if (st) st.textContent = STATUS_LABEL[status] || status;
      if (dt) dt.textContent = detailText(status);
      // Mobile status text
      window.slRestoreMobileLcd();
    }

    // LED ticker: start scroll if text overflows container
  function startTicker() {
    var ticker = document.getElementById('slNpTicker');
    var inner  = document.getElementById('slNpTickerInner');
    if (!ticker || !inner) return;
    inner.classList.remove('is-scrolling');
    inner.style.removeProperty('--sl-scroll-px');
    requestAnimationFrame(function() {
      var overflow = inner.scrollWidth - ticker.offsetWidth;
      if (overflow > 6) {
        inner.style.setProperty('--sl-scroll-px', '-' + overflow + 'px');
        inner.classList.add('is-scrolling');
      }
    });
  }

  // Right LCD: mode label + now-playing block or explanatory text
    var rst   = document.getElementById('slLastTitle');
    var rdt   = document.getElementById('slLastArtist');
    var npBlock  = document.getElementById('slNowPlayingBlock');
    var npTitle  = document.getElementById('slNowPlayingTitle');
    var npArtist = document.getElementById('slNowPlayingArtist');
    if (rst) rst.textContent = RIGHT_STATUS_LABEL[status] || status;
    if (rdt) rdt.textContent = rightDetailText(status);
    if (status === 'djjukebox_active') {
      var songTitle  = lastSongData.lastPlayed;
      var songArtist = lastSongData.lastPlayedArtist;
      if (songTitle) {
        if (npTitle)  npTitle.textContent  = songTitle;
        if (npArtist) npArtist.textContent = songArtist || '';
        if (npBlock) npBlock.style.display = '';
        startTicker();
      } else {
        if (npBlock) npBlock.style.display = 'none';
      }
    } else {
      if (npBlock) npBlock.style.display = 'none';
    }

    updateKpiVisibility(status);
  }

  // Expose for preview restore
  window.slRestoreLcd = function() {
    applyStatus(currentStatus, lastSongData.nowPlaying, lastSongData.lastPlayed, lastSongData.songsPlayed);
  };
  window.slCurrentStatus = currentStatus;

  // Init on page load
  updateKpiVisibility(currentStatus);
  if (currentStatus === 'djjukebox_active') startTicker();
  updateMobileNowPlaying(currentStatus);

  function pollStatus() {
    fetch(POLL_URL, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(data) {
        if (!data) return;

        if (data.party_status !== currentStatus) {
          window.location.reload();
          return;
        }

        // Cache song data
        lastSongData.nowPlaying       = data.now_playing_title   || '';
        lastSongData.nowPlayingArtist = data.now_playing_artist  || '';
        lastSongData.lastPlayed       = data.last_played_title   || '';
        lastSongData.lastPlayedArtist = data.last_played_artist  || '';
        lastSongData.songsPlayed      = data.songs_played        || 0;

        applyStatus(data.party_status, lastSongData.nowPlaying, lastSongData.lastPlayed, lastSongData.songsPlayed);

        // Update left KPIs
        var el;
        el = document.getElementById('slLTemes');    if (el) el.textContent = data.total_songs;
        el = document.getElementById('slLUsuaris');  if (el) el.textContent = data.active_users;
        el = document.getElementById('slLVotsMeus'); if (el) el.textContent = data.votes_left;
        el = document.getElementById('slLCoins');    if (el) el.textContent = data.credits;
        el = document.getElementById('slLVots');     if (el) el.textContent = data.total_votes;
        el = document.getElementById('slLPosades');  if (el) el.textContent = data.songs_played;
        el = document.getElementById('slLVotsF');    if (el) el.textContent = data.total_votes;

        // Update right KPIs
        el = document.getElementById('slRTemes');     if (el) el.textContent = data.total_songs;
        el = document.getElementById('slRPosades');   if (el) el.textContent = data.songs_played;
        el = document.getElementById('slRPeticions'); if (el) el.textContent = data.pending_requests_count;
        el = document.getElementById('slRMyPlayed');  if (el) el.textContent = data.my_played_votes;

        // Update mobile KPIs
        el = document.getElementById('slMobVots');     if (el) el.textContent = data.votes_left;
        el = document.getElementById('slMobCoins');    if (el) el.textContent = data.credits;
        el = document.getElementById('slMobFets');     if (el) el.textContent = data.user_votes_count;
        el = document.getElementById('slMobPosades');  if (el) el.textContent = data.songs_played;
        el = document.getElementById('slMobTotal');    if (el) el.textContent = data.total_votes;
        el = document.getElementById('slMobFetsF');    if (el) el.textContent = data.user_votes_count;
        el = document.getElementById('slMobPosadesB'); if (el) el.textContent = data.songs_played;
        el = document.getElementById('slMobRestants'); if (el) el.textContent = data.songs_remaining;
        el = document.getElementById('slMobPeticions');if (el) el.textContent = data.pending_requests_count;
        el = document.getElementById('slMobUsuarisB'); if (el) el.textContent = data.active_users;
        el = document.getElementById('slMobMyPlayed'); if (el) el.textContent = data.my_played_votes;
      })
      .catch(function() {});
  }

  setInterval(pollStatus, 5000);
})();

// AJAX voting — intercepts all vote/unvote forms so the page doesn't reload
(function() {
  var csrfToken = window.JukeboxConfig.csrfToken;

  function buildDesktopControls(songId, userVote, votesLeft, credits) {
    var canVote = votesLeft > 0 || credits > 0;
    if (!canVote && !userVote) {
      return '<div class="songs-vote-controls">'
        + '<button class="songs-vote-btn songs-vote-btn-locked" disabled><span class="material-symbols-outlined">keyboard_arrow_up</span></button>'
        + '<button class="songs-vote-btn songs-vote-btn-locked" disabled><span class="material-symbols-outlined">keyboard_arrow_down</span></button>'
        + '</div>';
    }
    if (userVote === 'like') {
      return '<div class="songs-vote-controls">'
        + '<form method="post" class="d-inline m-0 ajax-vote-form"><input type="hidden" name="csrfmiddlewaretoken" value="' + csrfToken + '"><input type="hidden" name="unvote_song_id" value="' + songId + '">'
        + '<button type="submit" class="songs-vote-btn songs-vote-btn-active songs-vote-btn-active-positive"><span class="material-symbols-outlined" style="font-variation-settings:\'FILL\' 1">keyboard_arrow_up</span></button></form>'
        + '<button class="songs-vote-btn songs-vote-btn-locked" disabled><span class="material-symbols-outlined">keyboard_arrow_down</span></button>'
        + '</div>';
    }
    if (userVote === 'dislike') {
      return '<div class="songs-vote-controls">'
        + '<button class="songs-vote-btn songs-vote-btn-locked" disabled><span class="material-symbols-outlined">keyboard_arrow_up</span></button>'
        + '<form method="post" class="d-inline m-0 ajax-vote-form"><input type="hidden" name="csrfmiddlewaretoken" value="' + csrfToken + '"><input type="hidden" name="unvote_song_id" value="' + songId + '">'
        + '<button type="submit" class="songs-vote-btn songs-vote-btn-active songs-vote-btn-active-negative"><span class="material-symbols-outlined" style="font-variation-settings:\'FILL\' 1">keyboard_arrow_down</span></button></form>'
        + '</div>';
    }
    return '<div class="songs-vote-controls">'
      + '<form method="post" class="d-inline m-0 ajax-vote-form"><input type="hidden" name="csrfmiddlewaretoken" value="' + csrfToken + '"><input type="hidden" name="vote_song_id" value="' + songId + '"><input type="hidden" name="vote_type" value="like">'
      + '<button type="submit" class="songs-vote-btn songs-vote-btn-positive"><span class="material-symbols-outlined">keyboard_arrow_up</span></button></form>'
      + '<form method="post" class="d-inline m-0 ajax-vote-form"><input type="hidden" name="csrfmiddlewaretoken" value="' + csrfToken + '"><input type="hidden" name="vote_song_id" value="' + songId + '"><input type="hidden" name="vote_type" value="dislike">'
      + '<button type="submit" class="songs-vote-btn songs-vote-btn-negative"><span class="material-symbols-outlined">keyboard_arrow_down</span></button></form>'
      + '</div>';
  }

  function buildMobileControls(songId, userVote, votesLeft, credits) {
    var canVote = votesLeft > 0 || credits > 0;
    if (!canVote && !userVote) {
      return '<a href="/ca/buy-coins/" class="text-decoration-none pe-0 mobile-vote-controls">'
        + '<span class="mobile-vote-btn mobile-vote-btn-locked"><i class="fas fa-caret-up"></i></span>'
        + '<span class="mobile-vote-btn mobile-vote-btn-locked"><i class="fas fa-caret-down"></i></span></a>';
    }
    if (userVote === 'like') {
      return '<div class="mobile-vote-controls">'
        + '<form method="post" class="m-0 ajax-vote-form"><input type="hidden" name="csrfmiddlewaretoken" value="' + csrfToken + '"><input type="hidden" name="unvote_song_id" value="' + songId + '">'
        + '<button type="submit" class="mobile-vote-btn mobile-vote-btn-positive mobile-vote-btn-active"><i class="fas fa-caret-up"></i></button></form>'
        + '<button class="mobile-vote-btn mobile-vote-btn-locked" disabled><i class="fas fa-caret-down"></i></button>'
        + '</div>';
    }
    if (userVote === 'dislike') {
      return '<div class="mobile-vote-controls">'
        + '<button class="mobile-vote-btn mobile-vote-btn-locked" disabled><i class="fas fa-caret-up"></i></button>'
        + '<form method="post" class="m-0 ajax-vote-form"><input type="hidden" name="csrfmiddlewaretoken" value="' + csrfToken + '"><input type="hidden" name="unvote_song_id" value="' + songId + '">'
        + '<button type="submit" class="mobile-vote-btn mobile-vote-btn-negative mobile-vote-btn-active"><i class="fas fa-caret-down"></i></button></form>'
        + '</div>';
    }
    return '<div class="mobile-vote-controls">'
      + '<form method="post" class="m-0 ajax-vote-form"><input type="hidden" name="csrfmiddlewaretoken" value="' + csrfToken + '"><input type="hidden" name="vote_song_id" value="' + songId + '"><input type="hidden" name="vote_type" value="like">'
      + '<button type="submit" class="mobile-vote-btn mobile-vote-btn-positive"><i class="fas fa-caret-up"></i></button></form>'
      + '<form method="post" class="m-0 ajax-vote-form"><input type="hidden" name="csrfmiddlewaretoken" value="' + csrfToken + '"><input type="hidden" name="vote_song_id" value="' + songId + '"><input type="hidden" name="vote_type" value="dislike">'
      + '<button type="submit" class="mobile-vote-btn mobile-vote-btn-negative"><i class="fas fa-caret-down"></i></button></form>'
      + '</div>';
  }

  function updateRowFromResponse(data) {
    // Desktop row
    var tr = document.querySelector('tr.pending-song-row[data-song-id="' + data.song_id + '"]');
    if (tr) {
      var votesCell = tr.querySelector('.songs-table-votes-count');
      if (votesCell) votesCell.textContent = data.num_likes;
      var badgeEl = tr.querySelector('td .badge');
      if (badgeEl && data.badge_label) {
        badgeEl.textContent = data.badge_label;
        badgeEl.style.backgroundColor = data.badge_bg;
        badgeEl.style.color = data.badge_text;
      }
      var controlsCell = tr.querySelector('.songs-table-cell-last');
      if (controlsCell) {
        controlsCell.innerHTML = buildDesktopControls(data.song_id, data.user_vote, data.votes_left, data.credits);
        attachHandlers(controlsCell);
      }
    }
    // Mobile card
    var card = document.querySelector('.mobile-bag-song-card[data-song-id="' + data.song_id + '"]');
    if (card) {
      var mobileBadge = card.querySelector('.badge');
      if (mobileBadge && data.badge_label) {
        mobileBadge.textContent = data.badge_label;
        mobileBadge.style.backgroundColor = data.badge_bg;
        mobileBadge.style.color = data.badge_text;
      }
      var mobileControls = card.querySelector('.mobile-vote-controls, a.text-decoration-none');
      if (mobileControls) {
        var parent = mobileControls.parentElement;
        parent.innerHTML = buildMobileControls(data.song_id, data.user_vote, data.votes_left, data.credits);
        attachHandlers(parent);
      }
    }
  }

  function handleVoteForm(form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var formData = new FormData(form);
      var btn = form.querySelector('button[type=submit]');
      if (btn) btn.disabled = true;
      fetch(window.location.pathname, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: formData,
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.success) {
          updateRowFromResponse(data);
        } else if (data.error) {
          // Show error briefly without reloading
          var msg = document.createElement('div');
          msg.className = 'alert alert-warning alert-dismissible fade show position-fixed';
          msg.style.cssText = 'top:1rem;left:50%;transform:translateX(-50%);z-index:9999;min-width:280px;';
          msg.innerHTML = data.error + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
          document.body.appendChild(msg);
          setTimeout(function() { msg.remove(); }, 4000);
          if (btn) btn.disabled = false;
        }
      })
      .catch(function() { if (btn) btn.disabled = false; });
    });
  }

  function attachHandlers(root) {
    (root || document).querySelectorAll('form.ajax-vote-form').forEach(handleVoteForm);
  }

  // Mark existing forms and attach
  document.querySelectorAll('form').forEach(function(f) {
    if (f.querySelector('[name=vote_song_id], [name=unvote_song_id]')) {
      f.classList.add('ajax-vote-form');
      handleVoteForm(f);
    }
  });
})();
