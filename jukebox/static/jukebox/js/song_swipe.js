function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Spotify Web Playback SDK Variables (always declared, initialized only if Spotify enabled)
const HAS_SPOTIFY_PLAYER = window.JukeboxSwipeConfig.hasSpotify;
let spotifyPlayer = null;
let spotifyDeviceId = null;
let SPOTIFY_TOKEN = null;
let spotifySdkReady = false;
let spotifyPlayerInitPromise = null;

window.onSpotifyWebPlaybackSDKReady = () => {
  spotifySdkReady = true;
};

function ensureSpotifyPlayer() {
  if (spotifyPlayer && spotifyDeviceId) {
    return Promise.resolve(spotifyPlayer);
  }

  if (!spotifySdkReady || !window.Spotify) {
    showMessage('El reproductor de Spotify no està llest. Espera uns segons...', false);
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

      fetch('https://api.spotify.com/v1/me/player', {
        headers: { 'Authorization': `Bearer ${SPOTIFY_TOKEN}` }
      }).then(response => {
        if (response.status === 401) {
          console.warn('[SPOTIFY] Token invalid - user needs to reconnect');
          showMessage('⚠️ Reconnecta el teu compte de Spotify des del perfil per activar la reproducció completa', false);
        }
      });

      resolve(spotifyPlayer);
    });

    spotifyPlayer.addListener('not_ready', ({ device_id }) => {
      console.log('[SPOTIFY] Device ID has gone offline:', device_id);
    });

    spotifyPlayer.addListener('player_state_changed', state => {
      if (!state) return;

      isPlaying = !state.paused;
      updatePlayButton();
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
      return response;
    } else if (response.status === 403) {
      console.error('[SPOTIFY] Premium required:', response.status);
      showMessage('Necessites Spotify Premium per reproduir cançons completes', false);
      throw new Error('Premium required');
    } else if (response.status === 401) {
      console.error('[SPOTIFY] Unauthorized:', response.status);
      showMessage('Sessió de Spotify caducada. Torna a connectar el teu compte.', false);
      throw new Error('Unauthorized');
    } else {
      console.error('[SPOTIFY] Error playing track:', response.status);
      showMessage('Error reproduint la cançó. Torna-ho a provar.', false);
      throw new Error('Playback error');
    }
  }).catch(error => {
    console.error('[SPOTIFY] Fetch error:', error);
    throw error;
  });
}

}

document.addEventListener('DOMContentLoaded', function() {
  // Detectar si és mòbil o desktop
  const isMobile = window.innerWidth < 768;
  const totalSongs = window.JukeboxSwipeConfig.totalSongs;
  const initialCompleted = window.JukeboxSwipeConfig.swipedCount;

  const cardStack = document.getElementById(isMobile ? 'card-stack' : 'card-stack-desktop');
  const cards = cardStack ? cardStack.querySelectorAll('.swipe-card') : [];
  const messageArea = document.getElementById(isMobile ? 'message-area' : 'message-area-desktop');
  const votesCount = document.getElementById('votes-count');
  const creditsCount = document.getElementById('credits-count');
  const progressBar = document.getElementById(isMobile ? 'progress-bar' : 'progress-bar-desktop');
  const progressText = document.getElementById(isMobile ? 'progress-text' : 'progress-text-desktop');
  const remainingCount = document.getElementById(isMobile ? 'remaining-count' : 'remaining-count-desktop');
  const undoBtn = document.getElementById('undo-btn');

  let currentIndex = 0;
  let lastAction = null; // { type: 'like'|'skip', songId: X, index: Y }
  const totalCards = cards.length;

  function updateZeroStatCards(votesLeft, credits) {
    var votesCard = document.getElementById('votes-stat-card');
    var votesIcon = document.getElementById('votes-icon');
    var votesEl = document.getElementById('votes-count');
    var creditsCard = document.getElementById('credits-stat-card');
    var creditsIcon = document.getElementById('credits-icon');
    var creditsEl = document.getElementById('credits-count');
    if (votesCard && votesEl) {
      if (parseInt(votesLeft) <= 0) {
        votesCard.style.background = 'rgba(0,64,224,0.08)';
        votesCard.style.borderColor = 'rgba(0,64,224,0.22)';
        votesCard.style.flexDirection = 'column'; votesCard.style.gap = '0.1rem';
        if (votesIcon) { votesIcon.style.color = '#0040e0'; votesIcon.style.fontSize = '0.8rem'; }
        votesEl.style.fontSize = '0.52rem'; votesEl.style.lineHeight = '1.2';
        votesEl.style.textAlign = 'center'; votesEl.style.color = '#0040e0';
        votesEl.innerHTML = 'Aconsegueix<br>vots';
      } else {
        votesCard.style.background = ''; votesCard.style.borderColor = '';
        votesCard.style.flexDirection = 'row'; votesCard.style.gap = '0.25rem';
        if (votesIcon) { votesIcon.style.color = '#5e24e1'; votesIcon.style.fontSize = '0.85rem'; }
        votesEl.style.fontSize = '0.8rem'; votesEl.style.lineHeight = '';
        votesEl.style.textAlign = ''; votesEl.style.color = '#191c1f';
        votesEl.textContent = votesLeft;
      }
    }
    if (creditsCard && creditsEl) {
      if (parseInt(credits) <= 0) {
        creditsCard.style.background = 'rgba(0,64,224,0.08)';
        creditsCard.style.borderColor = 'rgba(0,64,224,0.22)';
        creditsCard.style.flexDirection = 'column'; creditsCard.style.gap = '0.1rem';
        if (creditsIcon) { creditsIcon.style.color = '#0040e0'; creditsIcon.style.fontSize = '0.8rem'; }
        creditsEl.style.fontSize = '0.52rem'; creditsEl.style.lineHeight = '1.2';
        creditsEl.style.textAlign = 'center'; creditsEl.style.color = '#0040e0';
        creditsEl.innerHTML = 'Compra<br>Coins';
      } else {
        creditsCard.style.background = ''; creditsCard.style.borderColor = '';
        creditsCard.style.flexDirection = 'row'; creditsCard.style.gap = '0.25rem';
        if (creditsIcon) { creditsIcon.style.color = '#006875'; creditsIcon.style.fontSize = '0.85rem'; }
        creditsEl.style.fontSize = '0.8rem'; creditsEl.style.lineHeight = '';
        creditsEl.style.textAlign = ''; creditsEl.style.color = '#191c1f';
        creditsEl.textContent = credits;
      }
    }
  }

  if (!cardStack || cards.length === 0) return;

  // Actualitzar progrés
  function updateProgress() {
    const completedCount = initialCompleted + currentIndex;
    const progress = totalSongs > 0 ? (completedCount / totalSongs) * 100 : 0;
    const remaining = totalCards - currentIndex;

    if (progressBar) progressBar.style.width = progress + '%';
    if (progressText) progressText.textContent = `${completedCount} de ${totalSongs}`;
    if (remainingCount) remainingCount.textContent = remaining;
  }

  // Audio Management (Spotify SDK or Preview)
  const audioElement = document.getElementById('preview-audio');
  const playBtn = document.getElementById(isMobile ? 'play-preview-btn' : 'play-preview-btn-desktop');
  let isPlaying = false;
  let currentSpotifyId = null;

  function updatePlayButton() {
    if (!playBtn) return;
    const iIcon = playBtn.querySelector('i');
    if (iIcon) {
      if (isPlaying) {
        iIcon.classList.remove('fa-play');
        iIcon.classList.add('fa-pause');
      } else {
        iIcon.classList.remove('fa-pause');
        iIcon.classList.add('fa-play');
      }
      return;
    }
    const spanIcon = playBtn.querySelector('.material-symbols-outlined');
    if (spanIcon) {
      spanIcon.textContent = isPlaying ? 'pause' : 'play_arrow';
    }
  }

  function loadCurrentPreview() {
    if (currentIndex >= cards.length) return;

    const currentCard = cards[currentIndex];
    const previewUrl = currentCard.dataset.previewUrl;
    currentSpotifyId = currentCard.dataset.spotifyId || null;

    // If user has Spotify SDK, always show play button
    if (HAS_SPOTIFY_PLAYER) {
      if (playBtn) {
        playBtn.style.display = '';
        playBtn.style.opacity = '1';
        playBtn.disabled = false;
      }
    } else {
      // Fallback to preview URLs
      if (audioElement && previewUrl) {
        audioElement.src = previewUrl;
        audioElement.load();
        if (playBtn) {
          playBtn.style.display = '';
          playBtn.style.opacity = '1';
          playBtn.disabled = false;
        }
      } else {
        // No preview available
        if (playBtn) {
          playBtn.style.display = 'none';
        }
      }
    }
  }

  function stopAudio() {
    if (HAS_SPOTIFY_PLAYER && spotifyPlayer) {
      spotifyPlayer.pause().then(() => {
        isPlaying = false;
        updatePlayButton();
      });
    } else if (audioElement) {
      audioElement.pause();
      audioElement.currentTime = 0;
      audioElement.removeAttribute('src');
      audioElement.load();
      isPlaying = false;
      updatePlayButton();
    }
  }

  function cleanupPlaybackSession() {
    if (HAS_SPOTIFY_PLAYER && spotifyPlayer) {
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

    if (audioElement) {
      audioElement.pause();
      audioElement.currentTime = 0;
      audioElement.removeAttribute('src');
      audioElement.load();
    }

    isPlaying = false;
    updatePlayButton();
  }

  function getCurrentSongSpotifyId() {
    if (currentIndex >= cards.length) return null;
    const currentCard = cards[currentIndex];
    // Get spotify_id from data attribute
    return currentCard.dataset.spotifyId || null;
  }

  if (playBtn) {
    playBtn.addEventListener('click', function(e) {
      e.stopPropagation();

      if (currentIndex >= cards.length) return;

      if (HAS_SPOTIFY_PLAYER) {
        // Use Spotify Web Playback SDK
        const spotifyId = getCurrentSongSpotifyId();
        if (!spotifyId) {
          showMessage('Error: No s\'ha pogut obtenir l\'ID de Spotify', false);
          return;
        }

        if (isPlaying) {
          ensureSpotifyPlayer().then(() => spotifyPlayer.pause()).then(() => {
            isPlaying = false;
            updatePlayButton();
          });
        } else {
          playSpotifyTrack(spotifyId).then(() => {
            isPlaying = true;
            updatePlayButton();
          }).catch(() => {
            isPlaying = false;
            updatePlayButton();
          });
        }
      } else {
        // Fallback: Use preview URLs
        const currentCard = cards[currentIndex];
        const previewUrl = currentCard.dataset.previewUrl;

        if (!previewUrl) {
          showMessage('Preview no disponible per aquesta cançó', false);
          return;
        }

        if (isPlaying) {
          audioElement.pause();
          isPlaying = false;
        } else {
          audioElement.play().catch(err => {
            console.error('Error playing audio:', err);
            showMessage('Error reproduint preview', false);
          });
          isPlaying = true;
        }
        updatePlayButton();
      }
    });

    // Preview audio events (only for non-Spotify users)
    if (!HAS_SPOTIFY_PLAYER && audioElement) {
      audioElement.addEventListener('ended', function() {
        isPlaying = false;
        updatePlayButton();
      });

      audioElement.addEventListener('pause', function() {
        isPlaying = false;
        updatePlayButton();
      });

      audioElement.addEventListener('play', function() {
        isPlaying = true;
        updatePlayButton();
      });
    }
  }

  // Inicialitzar cartes: primera visible, resta ocultes
  cards.forEach((card, index) => {
    if (index === 0) {
      card.classList.remove('d-none');
      card.style.zIndex = '10';
      if (isMobile) {
        card.style.display = 'flex';
      }
    } else {
      card.classList.add('d-none');
      if (isMobile) {
        card.style.display = 'none';
      }
    }
  });

  // Load preview for first card
  loadCurrentPreview();
  updateProgress();

  window.addEventListener('pagehide', cleanupPlaybackSession);
  window.addEventListener('beforeunload', cleanupPlaybackSession);
  document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
      cleanupPlaybackSession();
    }
  });

  // Afegir event listeners als botons (fora de cada carta en mòbil, dins en desktop)
  if (isMobile) {
    const btnSkip = document.getElementById('mobile-skip-btn');
    const btnLike = document.getElementById('mobile-like-btn');

    if (btnSkip) {
      btnSkip.addEventListener('click', function(e) {
        e.stopPropagation();
        handleSkip();
      });
    }

    if (btnLike) {
      btnLike.addEventListener('click', function(e) {
        e.stopPropagation();
        handleLike();
      });
    }
  } else {
    // Desktop: botons dins de cada carta
    cards.forEach((card) => {
      const btnSkip = card.querySelector('.btn-skip-card');
      const btnLike = card.querySelector('.btn-like-card');

      if (btnSkip) {
        btnSkip.addEventListener('click', function(e) {
          e.stopPropagation();
          handleSkip();
        });
      }

      if (btnLike) {
        btnLike.addEventListener('click', function(e) {
          e.stopPropagation();
          handleLike();
        });
      }
    });
  }

  function showMessage(text, isSuccess = true) {
    messageArea.innerHTML = `<div class="alert ${isSuccess ? 'alert-success' : 'alert-danger'}" style="font-size:0.85rem; padding: 0.5rem 0.75rem;">${escapeHtml(text)}</div>`;
    setTimeout(() => { messageArea.innerHTML = ''; }, 3000);
  }

  function showVoteMessage(voteType, badgeLabel) {
    var text = '';
    var isLike = voteType === 'like';
    if (voteType === 'like') {
      text = 'Has votat que t\'ha agradat';
    } else {
      text = 'Has votat que no t\'ha agradat';
    }
    if (badgeLabel && badgeLabel !== 'INTACTA') text += ' · ' + badgeLabel;
    messageArea.innerHTML = `<div style="font-size:0.85rem; padding:0.5rem 0.75rem; border-radius:8px; background:${isLike ? '#f0fdf4' : '#fef2f2'}; color:${isLike ? '#166534' : '#991b1b'}; border: 1px solid ${isLike ? '#bbf7d0' : '#fecaca'};">${escapeHtml(text)}</div>`;
    setTimeout(() => { messageArea.innerHTML = ''; }, 3000);
  }

  function nextCard() {
    if (currentIndex >= cards.length) {
      // No més cançons
      stopAudio();
      const cardStack = document.getElementById(isMobile ? 'card-stack' : 'card-stack-desktop');
      if (cardStack) {
        cardStack.innerHTML = `
        <div class="card shadow-lg" style="border-radius: 1.5rem;">
          <div class="card-body text-center p-5">
            <i class="fas fa-check-circle fa-5x text-success mb-4"></i>
            <h4 class="mb-3">Has fet match amb totes les cançons disponibles!</h4>
            <p class="text-muted mb-4">Torna a la llista per veure els resultats</p>
            <a href=window.JukeboxSwipeConfig.songListUrl class="btn btn-primary btn-lg">
              <i class="fas fa-list me-2"></i>Veure llista
            </a>
          </div>
        </div>
      `;
      }
      return;
    }

    // Mostrar la següent carta
    const nextCardElement = cards[currentIndex];
    nextCardElement.classList.remove('d-none');
    if (isMobile) {
      nextCardElement.style.display = 'flex';
    }
    nextCardElement.style.zIndex = currentIndex + 10;
    nextCardElement.style.transform = '';
    nextCardElement.style.opacity = '1';

    // Load preview for next card
    loadCurrentPreview();
  }

  function animateCardOut(direction, songId, actionType) {
    const card = cards[currentIndex];
    const transform = direction === 'left' ? 'translateX(-150%) rotate(-30deg)' : 'translateX(150%) rotate(30deg)';

    // Stop audio when card goes out
    stopAudio();

    // Guardar acció per undo
    lastAction = {
      type: actionType,
      songId: songId,
      index: currentIndex,
      card: card
    };

    // Mostrar botó undo
    if (undoBtn) {
      undoBtn.style.display = 'block';
      // Ocultar després de 3 segons
      setTimeout(() => {
        if (lastAction && lastAction.index === currentIndex - 1) {
          undoBtn.style.display = 'none';
          lastAction = null;
        }
      }, 3000);
    }

    // Animar la carta cap a fora
    card.style.transform = transform;
    card.style.opacity = '0';
    card.style.zIndex = '1'; // Enviar al fons

    setTimeout(() => {
      // Ocultar completament i resetar
      card.classList.add('d-none');
      card.style.transform = '';
      card.style.opacity = '1';

      // Avançar a la següent
      currentIndex++;
      updateProgress();
      nextCard();
    }, 300);
  }

  // Funcionalitat Undo
  if (undoBtn) {
    undoBtn.addEventListener('click', function() {
      if (!lastAction) return;

      // Tornar a l'índex anterior
      currentIndex = lastAction.index;

      // Mostrar la carta anterior
      const card = lastAction.card;
      card.classList.remove('d-none');
      card.style.zIndex = currentIndex + 10;
      card.style.transform = '';
      card.style.opacity = '1';

      // Ocultar la següent carta si existeix
      if (cards[currentIndex + 1]) {
        cards[currentIndex + 1].classList.add('d-none');
      }

      // Actualitzar progrés
      updateProgress();

      // Ocultar botó undo
      undoBtn.style.display = 'none';
      showMessage('Acció desfeta', true);
      lastAction = null;
    });
  }

  function disableCurrentButtons(disabled) {
    const currentCard = cards[currentIndex];
    if (!currentCard) return;
    const btnSkip = currentCard.querySelector('.btn-skip-card');
    const btnLike = currentCard.querySelector('.btn-like-card');
    if (btnSkip) btnSkip.disabled = disabled;
    if (btnLike) btnLike.disabled = disabled;
  }

  function handleSkip() {
    if (currentIndex >= cards.length) return;

    const songId = cards[currentIndex].dataset.songId;

    // Deshabilitar botons mentre processa
    disableCurrentButtons(true);

    fetch(window.JukeboxSwipeConfig.swipeUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': window.JukeboxSwipeConfig.csrfToken
      },
      body: new URLSearchParams({
        action: 'skip',
        song_id: songId
      })
    })
    .then(function(response) {
      if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) {
        window.location.reload();
        return null;
      }
      return response.json();
    })
    .then(function(data) {
      if (!data) return;
      if (data.success) {
        updateZeroStatCards(data.votes_left, data.credits);
        const votesCountDesktop = document.getElementById('votes-count-desktop');
        const creditsCountDesktop = document.getElementById('credits-count-desktop');
        if (votesCountDesktop) votesCountDesktop.textContent = data.votes_left;
        if (creditsCountDesktop) creditsCountDesktop.textContent = data.credits;
        showVoteMessage('dislike', data.badge_label || '');
        animateCardOut('left', songId, 'skip');
        setTimeout(() => { disableCurrentButtons(false); }, 350);
      } else {
        showMessage(data.error || 'Error al saltar la cançó', false);
        disableCurrentButtons(false);
      }
    })
    .catch(function(error) {
      console.error('Skip error:', error);
      showMessage('No s\'ha pogut saltar · comprova la connexió', false);
      disableCurrentButtons(false);
    });
  }

  function handleLike() {
    if (currentIndex >= cards.length) return;

    const songId = cards[currentIndex].dataset.songId;

    // Deshabilitar botons mentre processa
    disableCurrentButtons(true);

    fetch(window.JukeboxSwipeConfig.swipeUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': window.JukeboxSwipeConfig.csrfToken
      },
      body: new URLSearchParams({
        action: 'like',
        song_id: songId
      })
    })
    .then(function(response) {
      if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) {
        // Sessió caducada o resposta inesperada → reload
        window.location.reload();
        return null;
      }
      return response.json();
    })
    .then(function(data) {
      if (!data) return;
      if (data.success) {
        updateZeroStatCards(data.votes_left, data.credits);
        const votesCountDesktop = document.getElementById('votes-count-desktop');
        const creditsCountDesktop = document.getElementById('credits-count-desktop');
        const userLikesCount = document.getElementById('user-likes-count');
        if (votesCountDesktop) votesCountDesktop.textContent = data.votes_left;
        if (creditsCountDesktop) creditsCountDesktop.textContent = data.credits;
        if (userLikesCount && data.user_likes_count !== undefined) userLikesCount.textContent = data.user_likes_count;
        showVoteMessage('like', data.badge_label || '');
        animateCardOut('right', songId, 'like');
        setTimeout(() => { disableCurrentButtons(false); }, 350);
      } else {
        showMessage(data.error || 'Error al fer match', false);
        disableCurrentButtons(false);
      }
    })
    .catch(function(error) {
      console.error('Like error:', error);
      showMessage('No s\'ha pogut votar · comprova la connexió', false);
      disableCurrentButtons(false);
    });
  }

  // Suport per gestos de lliscament en mòbil amb feedback visual
  let touchStartX = 0;
  let touchStartY = 0;
  let touchCurrentX = 0;
  let isDragging = false;

  cardStack.addEventListener('touchstart', function(e) {
    if (currentIndex >= cards.length) return;
    touchStartX = e.changedTouches[0].clientX;
    touchStartY = e.changedTouches[0].clientY;
    isDragging = true;
    var hint = document.getElementById('swipe-hint-wrapper');
    if (hint) { hint.style.transition = 'opacity 0.3s'; hint.style.opacity = '0'; setTimeout(function(){ hint.remove(); }, 300); }
  }, { passive: true });

  cardStack.addEventListener('touchmove', function(e) {
    if (!isDragging || currentIndex >= cards.length) return;

    touchCurrentX = e.changedTouches[0].clientX;
    const touchCurrentY = e.changedTouches[0].clientY;
    const diffX = touchCurrentX - touchStartX;
    const diffY = touchCurrentY - touchStartY;

    // Només fer swipe si el moviment és més horitzontal que vertical
    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 10) {
      e.preventDefault();

      const card = cards[currentIndex];
      const rotation = diffX / 20; // Rotació proporcional al desplaçament
      const opacity = 1 - Math.abs(diffX) / 400;

      card.style.transform = `translateX(${diffX}px) rotate(${rotation}deg)`;
      card.style.opacity = Math.max(0.5, opacity);
    }
  }, { passive: false });

  cardStack.addEventListener('touchend', function(e) {
    if (!isDragging || currentIndex >= cards.length) return;

    const touchEndX = e.changedTouches[0].clientX;
    const diff = touchEndX - touchStartX;

    isDragging = false;

    const card = cards[currentIndex];

    // Si el desplaçament és suficient (> 100px), fer swipe
    if (Math.abs(diff) > 100) {
      if (diff > 0) {
        // Swipe a la dreta = Like
        handleLike();
      } else {
        // Swipe a l'esquerra = Skip
        handleSkip();
      }
    } else {
      // Si no, tornar la carta a la posició original
      card.style.transform = '';
      card.style.opacity = '1';
    }
  }, { passive: true });

  // També suportar mouse drag per desktop
  let mouseStartX = 0;
  let isMouseDragging = false;

  cardStack.addEventListener('mousedown', function(e) {
    if (currentIndex >= cards.length) return;
    mouseStartX = e.clientX;
    isMouseDragging = true;
  });

  cardStack.addEventListener('mousemove', function(e) {
    if (!isMouseDragging || currentIndex >= cards.length) return;

    const diffX = e.clientX - mouseStartX;
    const card = cards[currentIndex];
    const rotation = diffX / 20;
    const opacity = 1 - Math.abs(diffX) / 400;

    if (Math.abs(diffX) > 10) {
      card.style.transform = `translateX(${diffX}px) rotate(${rotation}deg)`;
      card.style.opacity = Math.max(0.5, opacity);
    }
  });

  cardStack.addEventListener('mouseup', function(e) {
    if (!isMouseDragging || currentIndex >= cards.length) return;

    const diffX = e.clientX - mouseStartX;
    isMouseDragging = false;

    const card = cards[currentIndex];

    if (Math.abs(diffX) > 100) {
      if (diffX > 0) {
        handleLike();
      } else {
        handleSkip();
      }
    } else {
      card.style.transform = '';
      card.style.opacity = '1';
    }
  });

  cardStack.addEventListener('mouseleave', function() {
    if (isMouseDragging && currentIndex < cards.length) {
      const card = cards[currentIndex];
      card.style.transform = '';
      card.style.opacity = '1';
    }
    isMouseDragging = false;
  });
});
