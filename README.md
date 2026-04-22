# DJ Jukebox

![CI Tests](https://github.com/djkram/dj_jukebox/actions/workflows/ci.yml/badge.svg)
![CD Deploy](https://github.com/djkram/dj_jukebox/actions/workflows/cd.yml/badge.svg)

Una aplicació web interactiva que permet als DJs crear festes on els assistents poden votar les cançons que volen escoltar, utilitzant playlists de Spotify amb sistema de moneda virtual i notificacions en temps real.

## Característiques principals

### Per a usuaris

- **Sistema de vot dual**: Compra Coins i converteix-los en Vots amb bonificacions
- **Votació múltiple**:
  - Vista de llista tradicional amb totes les cançons
  - Vista "Busca Match": interfície tipus swipe per votar ràpidament
- **Peticions de cançons**: Cerca i demana cançons de Spotify que no estiguin a la playlist
- **Notificacions en temps real**: Rebràs avisos quan:
  - El DJ accepti la teva petició de cançó
  - Una cançó que has votat es reprodueixi (Match!)
  - Compris o rebis Coins
- **Autenticació amb Spotify**: Login amb el teu compte de Spotify
- **Pagaments segurs**: Compra Coins amb Stripe

### Per a DJs (superusuaris)

- **Gestió de festes**: Crea i configura esdeveniments amb codis d'accés únics
- **Integració amb Spotify**: Enllaça playlists de Spotify directament
- **Dashboard en temps real**: Visualitza les cançons més votades
- **Metadades musicals**: Veure BPM i clau Camelot per a mescles harmòniques
- **Gestió de peticions**: Accepta o rebutja peticions de cançons dels usuaris
- **Control de reproducció**: Marca cançons com a reproduïdes (notifica automàticament els votants)

## Tecnologies utilitzades

- **Backend**: Django 5.2 (Python)
- **Base de dades**: SQLite (desenvolupament)
- **Frontend**: Bootstrap 5 (SB Admin 2 theme)
- **Autenticació**: django-allauth (suport per OAuth de Spotify)
- **Pagaments**: Stripe
- **APIs externes**:
  - Spotify Web API (playlists, cerca, audio features)
  - GetSongBPM (fallback per BPM/key amb cerca difusa agressiva)
  - MusicBrainz (fallback secundari, base de dades col·laborativa)

## Instal·lació

### Requisits previs

- Python 3.12.x (recomanat)
- Compte de desenvolupador de Spotify
- Compte de Stripe (mode test per desenvolupament)
- Compte de Gmail per enviar correus de verificació

### Pas 1: Clonar el repositori

```bash
git clone https://github.com/yourusername/dj_jukebox.git
cd dj_jukebox
```

### Pas 2: Crear entorn virtual i instal·lar dependències

```bash
python3.12 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Pas 3: Configurar variables d'entorn

Crea un fitxer `.env` a l'arrel del projecte amb el següent contingut:

```env
# Spotify API
SPOTIFY_CLIENT_ID=el_teu_client_id
SPOTIFY_CLIENT_SECRET=el_teu_client_secret

# Stripe
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email
GMAIL_USER=el_teu_email@gmail.com
GMAIL_APP_PASSWORD=la_teva_app_password

# Django (opcional)
APP_ENV=development
DEBUG=True
LOG_LEVEL=DEBUG
SECRET_KEY=genera_una_clau_secreta_aleatoria
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

### Pas 4: Configurar Spotify OAuth

1. Ves a [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Crea una nova aplicació
3. Afegeix les següents Redirect URIs:
   - `http://127.0.0.1:8000/accounts/spotify/login/callback/`
   - `http://localhost:8000/accounts/spotify/login/callback/`
4. Copia el Client ID i Client Secret al fitxer `.env`

### Pas 5: Configurar Stripe

1. Crea un compte a [Stripe](https://stripe.com)
2. Activa el mode test
3. Copia les claus API al fitxer `.env`
4. Configura un webhook apuntant a `http://localhost:8000/stripe/webhook/`

### Pas 6: Inicialitzar la base de dades

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Pas 7: Executar el servidor

```bash
python manage.py runserver
```

L'aplicació estarà disponible a `http://127.0.0.1:8000`

## Ús

### Com a DJ (Superusuari)

1. **Connecta amb Spotify**: Inicia sessió i connecta el teu compte de Spotify
2. **Crea una festa**: Ves a `/dj/` i crea un nou esdeveniment
3. **Enllaça una playlist**: A la configuració de la festa, selecciona una playlist de Spotify
4. **Comparteix el codi**: Dona el codi d'accés de la festa als assistents
5. **Gestiona peticions**: Revisa i accepta/rebutja peticions de cançons a `/dj/manage-requests/`
6. **Dashboard**: Visualitza les cançons més votades i marca-les com a reproduïdes

### Com a usuari/assistent

1. **Registra't o inicia sessió**: Connecta amb Spotify o registra't amb email
2. **Selecciona una festa**: Tria la festa a la qual vols assistir
3. **Compra Coins**: Ves a "Compra Coins" per obtenir crèdits
4. **Converteix a Vots**: Converteix els teus Coins en Vots (amb bonificacions per paquets grans)
5. **Vota cançons**:
   - Llista: Navega i vota les teves cançons preferides
   - Busca Match: Swipe per votar ràpidament
6. **Demana cançons**: Cerca i demana cançons que no estiguin a la playlist
7. **Rebràs notificacions**: La campaneta et notificarà quan el DJ accepti les teves peticions o quan les teves cançons sonen

## Sistema de moneda

### Coins (Moneda global)

- Es compren amb diners reals via Stripe
- Són globals a totes les festes
- Es poden utilitzar per:
  - Convertir a Vots
  - Demanar cançons

### Vots (Per festa)

- Específics de cada festa
- Es generen convertint Coins amb bonificacions:
  - 1 Coin → 2 Vots
  - 2 Coins → 4 Vots
  - 3 Coins → 6 Vots
  - 5 Coins → 11 Vots (+1 bonus)
  - 10 Coins → 25 Vots (+5 bonus)
  - 20 Coins → 60 Vots (+20 bonus)

## Sistema d'Audio Features (BPM i Key)

L'aplicació utilitza un sistema de fallback en cascada per obtenir BPM i clau musical de les cançons:

### 1. Spotify Audio Features API (Primària)
- Font principal i més fiable
- Inclosa amb l'autenticació de Spotify
- Proporciona BPM precís i clau musical en format Spotify (0-11)
- Es converteix automàticament a notació Camelot per mescles harmòniques

### 2. GetSongBPM API (Secundària)
- S'activa quan Spotify no té les dades
- Utilitza 8 estratègies de cerca diferents:
  - Títol i artista complets
  - Títol simplificat (sense parèntesis/guions)
  - Només primer artista
  - Combinacions simplificades
  - Només títol
  - Sense accents ni diacrítics
  - Cerca de noms alternatius en parèntesis
- Requereix clau API: `GETSONGBPM_API_KEY` al fitxer `.env`

### 3. MusicBrainz (Terciària)
- Últim recurs quan les altres fallen
- Base de dades col·laborativa gratuïta
- Busca BPM i key als tags d'usuaris
- No requereix API key
- Menys fiable però útil per cançons obscures

### Exemple de configuració

```env
# Opcional: Per millorar cobertura de metadades
GETSONGBPM_API_KEY=la_teva_clau_api
```

Aquest sistema en cascada garanteix la màxima cobertura de metadades musicals per a tota mena de gèneres i èpoques.

## Estructura del projecte

```
dj_jukebox/
├── dj_jukebox/          # Configuració del projecte Django
│   ├── settings.py      # Configuració principal
│   ├── urls.py          # URLs del projecte
│   └── wsgi.py
├── jukebox/             # Aplicació principal
│   ├── models.py        # Models de dades (User, Party, Song, Vote, Notification, etc.)
│   ├── views.py         # Vistes i lògica de negoci
│   ├── forms.py         # Formularis
│   ├── spotify_api.py   # Integració amb Spotify
│   ├── votes.py         # Sistema de vots
│   ├── notifications.py # Sistema de notificacions
│   ├── context_processors.py  # Variables globals per templates
│   ├── templates/       # Plantilles HTML
│   └── static/          # CSS, JS, imatges
├── manage.py
├── requirements.txt
├── .env                 # Variables d'entorn (no al repo)
├── CLAUDE.md           # Guia per a desenvolupadors
└── README.md           # Aquest fitxer
```

## Models de dades principals

- **User**: Usuaris amb camp `credits` per Coins
- **Party**: Festes amb playlists, límits de vots, codis únics
- **Song**: Cançons amb metadades (BPM, clau Camelot), vots
- **Vote**: Relació many-to-many usuari-cançó-festa
- **SongRequest**: Peticions de cançons dels usuaris
- **Notification**: Notificacions del sistema
- **VotePackage**: Registres de compres de Coins

## API Endpoints principals

- `GET /` - Pàgina principal
- `GET /select-party/` - Seleccionar festa
- `GET /songs/` - Llista de cançons amb votació
- `GET /songs/swipe/` - Vista Busca Match
- `GET/POST /songs/request/` - Demanar cançons
- `GET /notifications/` - Veure notificacions
- `GET /buy-coins/` - Comprar Coins
- `POST /stripe/webhook/` - Webhook de Stripe
- `GET /dj/` - Backoffice del DJ (superusuari)
- `GET /dj/dashboard/` - Dashboard del DJ
- `GET/POST /dj/manage-requests/` - Gestionar peticions

## Desenvolupament

### Executar tests

```bash
# Executar tots els tests
python manage.py test jukebox

# Amb cobertura
coverage run --source='jukebox' manage.py test jukebox
coverage report
coverage html  # Genera report HTML
```

📚 **Guia completa de testing**: Consulta [.github/TESTING.md](.github/TESTING.md)

### CI/CD

El projecte utilitza **GitHub Actions** per CI/CD automàtic:

- **CI (Continuous Integration)**: Executa tests automàticament en cada push/PR
- **CD (Continuous Deployment)**: Desplega a Render només si els tests passen

**Workflows configurats:**
- `.github/workflows/ci.yml` - Tests automàtics
- `.github/workflows/cd.yml` - Deploy automàtic a Render

Per configurar CI/CD al teu repositori, consulta la [guia de testing](.github/TESTING.md#cicd-amb-github-actions).

### Crear migracions

```bash
python manage.py makemigrations
python manage.py migrate
```

### Accedir al shell de Django

```bash
python manage.py shell
```

### Accedir a l'admin de Django

Ves a `http://127.0.0.1:8000/admin/` i inicia sessió amb el superusuari.

## Contribuir

1. Fork el projecte
2. Crea una branca per a la teva funcionalitat (`git checkout -b feature/nova-funcionalitat`)
3. Commit els teus canvis (`git commit -m 'Afegeix nova funcionalitat'`)
4. Push a la branca (`git push origin feature/nova-funcionalitat`)
5. Obre un Pull Request

## Llicència

Aquest projecte està sota llicència MIT. Consulta el fitxer `LICENSE` per a més detalls.

## Crèdits

- **Music data**: Powered by [GetSongBPM](https://getsongbpm.com) and Spotify
- **UI Theme**: [SB Admin 2](https://startbootstrap.com/theme/sb-admin-2) by Start Bootstrap
- **Icons**: [Font Awesome](https://fontawesome.com/)

## Suport

Si tens problemes o preguntes, obre un issue al repositori de GitHub.

---

Fet amb ❤️ per a la comunitat de DJs i amants de la música
