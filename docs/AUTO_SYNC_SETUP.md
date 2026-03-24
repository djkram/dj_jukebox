# Auto-Sync Playlist Setup

## Configuració del Sistema d'Auto-Sincronització

El sistema d'auto-sincronització permet mantenir les playlists de Spotify sincronitzades automàticament amb la base de dades local cada 5 minuts.

---

## Configuració amb Cron (Recomanat per producció)

### 1. Editar crontab

```bash
crontab -e
```

### 2. Afegir entrada per sync cada 5 minuts

```bash
*/5 * * * * cd /path/to/dj_jukebox && /path/to/.venv/bin/python manage.py sync_playlists >> /var/log/dj_jukebox_sync.log 2>&1
```

**Exemple concret:**
```bash
*/5 * * * * cd /Users/kksq941/Code/dj_jukebox-main && /Users/kksq941/Code/dj_jukebox-main/.venv/bin/python manage.py sync_playlists >> /var/log/dj_jukebox_sync.log 2>&1
```

### 3. Verificar que cron està funcionant

```bash
# Veure logs
tail -f /var/log/dj_jukebox_sync.log

# Veure tasques cron actives
crontab -l
```

---

## Management Command

### Sincronitzar totes les festes

```bash
python manage.py sync_playlists
```

**Output exemple:**
```
Syncing all auto-sync enabled parties...

Total parties: 3
✓ Synced: 2
⊘ Skipped: 1
✗ Errors: 0

Sync completed!
```

### Sincronitzar només una festa específica

```bash
python manage.py sync_playlists --party-id 1
```

### Mode verbose (detalls de cada festa)

```bash
python manage.py sync_playlists --verbose
```

**Output exemple:**
```
Syncing all auto-sync enabled parties...

Total parties: 3
✓ Synced: 2
⊘ Skipped: 1

Detailed results:
  • Summer Party (#1): +5 -2
  • Birthday Bash (#2): +0 -0
  • Night Out (#3): skipped (Too soon)

Sync completed!
```

---

## Ús a la Interfície Web

### Activar Auto-Sync per una festa

1. Anar a **Party Settings** (`/party/<id>/settings/`)
2. Clicar el toggle **"Auto-sync Spotify"**
3. La playlist es sincronitzarà automàticament cada 5 minuts

### Forçar sincronització manual

1. A **Party Settings**, clicar **"Sync Now"**
2. Això ignora el rate limit i sincronitza immediatament

---

## Funcionament Tècnic

### Rate Limiting

- **Mínim interval:** 4 minuts entre syncs
- **Propòsit:** Evitar sobrecàrrega de l'API de Spotify
- **Bypass:** Usar `force_sync_playlist` endpoint o command `--force`

### Lògica de Sincronització

1. **Obtenir tracks de Spotify** via API
2. **Comparar amb BD local**:
   - Detectar cançons noves → Afegir
   - Detectar cançons eliminades → Eliminar
3. **Actualitzar timestamp** `last_sync_at`
4. **Logging** per debugging

### Camps BPM/Key

- Les cançons noves s'afegeixen sense BPM/Key
- Aquests es poden analitzar després amb **Auto-Analyze** (tasca #2)

---

## Endpoints API

### Toggle Auto-Sync

```http
POST /party/<id>/toggle-auto-sync/
```

**Resposta:**
```json
{
  "success": true,
  "auto_sync_enabled": true,
  "last_sync_at": "2026-03-19T18:30:00Z"
}
```

### Force Sync

```http
POST /party/<id>/force-sync/
```

**Resposta:**
```json
{
  "success": true,
  "added": 5,
  "removed": 2,
  "total": 103,
  "synced_at": "2026-03-19T18:35:00Z"
}
```

---

## Requisits

1. **Owner assignat:** La festa ha de tenir un `owner` (usuari que té Spotify connectat)
2. **Playlist assignada:** La festa ha de tenir una `playlist` vinculada
3. **Token Spotify vàlid:** L'owner ha de tenir Spotify OAuth connectat
4. **Auto-sync activat:** Camp `auto_sync_playlist=True`

---

## Troubleshooting

### Error: "Spotify account not connected"

- L'owner no té Spotify connectat
- **Solució:** Connectar Spotify a `/accounts/spotify/login/`

### Error: "No playlist assigned"

- La festa no té playlist vinculada
- **Solució:** Assignar playlist a Party Settings

### Error: "Too soon (rate limit)"

- Última sync fa menys de 4 minuts
- **Solució:** Esperar o usar `force_sync_playlist`

### Logs no apareixen

```bash
# Verificar permisos del fitxer de log
ls -la /var/log/dj_jukebox_sync.log

# Crear fitxer si no existeix
sudo touch /var/log/dj_jukebox_sync.log
sudo chown $USER:$USER /var/log/dj_jukebox_sync.log
```

### Cron no s'executa

```bash
# Verificar que cron està executant-se
ps aux | grep cron

# Verificar permisos d'execució
chmod +x manage.py

# Provar command manualment primer
cd /path/to/dj_jukebox && .venv/bin/python manage.py sync_playlists
```

---

## Monitorització

### Veure últimes sincronitzacions

```python
from jukebox.models import Party
from django.utils import timezone

parties = Party.objects.filter(auto_sync_playlist=True)
for party in parties:
    if party.last_sync_at:
        diff = timezone.now() - party.last_sync_at
        print(f"{party.name}: {int(diff.total_seconds() / 60)} minuts")
    else:
        print(f"{party.name}: Mai sincronitzat")
```

### Estadístiques de sincronització

Els logs inclouen:
- Nombre de cançons afegides
- Nombre de cançons eliminades
- Total de cançons després de sync
- Errors i motius de skip

---

## Configuració Alternativa: Systemd Timer (Linux)

Per servidors Linux moderns, es pot usar systemd en lloc de cron:

### 1. Crear service

```ini
# /etc/systemd/system/dj-jukebox-sync.service
[Unit]
Description=DJ Jukebox Playlist Sync
After=network.target

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/path/to/dj_jukebox
ExecStart=/path/to/.venv/bin/python manage.py sync_playlists
StandardOutput=journal
StandardError=journal
```

### 2. Crear timer

```ini
# /etc/systemd/system/dj-jukebox-sync.timer
[Unit]
Description=Run DJ Jukebox sync every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Unit=dj-jukebox-sync.service

[Install]
WantedBy=timers.target
```

### 3. Activar

```bash
sudo systemctl daemon-reload
sudo systemctl enable dj-jukebox-sync.timer
sudo systemctl start dj-jukebox-sync.timer
sudo systemctl status dj-jukebox-sync.timer
```

---

## Next Steps

Després d'implementar Auto-Sync, considera implementar **Auto-Analyze** (Task #2-Backend) per processar automàticament BPM/Key de les cançons noves.
