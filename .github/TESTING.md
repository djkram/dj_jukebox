# Testing Guide

## Executar Tests Localment

### 1. Activar l'entorn virtual

```bash
source venv/bin/activate  # macOS/Linux
# o
venv\Scripts\activate  # Windows
```

### 2. Instal·lar dependencies

```bash
pip install -r requirements.txt
pip install coverage  # Per veure cobertura de tests
```

### 3. Executar tots els tests

```bash
python manage.py test jukebox
```

### 4. Executar tests específics

```bash
# Només tests de notificacions
python manage.py test jukebox.tests.NotificationsTests

# Només un test concret
python manage.py test jukebox.tests.NotificationsTests.test_mark_notification_read_success
```

### 5. Executar amb cobertura

```bash
coverage run --source='jukebox' manage.py test jukebox
coverage report  # Veure report a la terminal
coverage html    # Generar report HTML
open htmlcov/index.html  # Obrir al navegador
```

## CI/CD amb GitHub Actions

### Workflows Configurats

#### 1. **CI - Tests** (`.github/workflows/ci.yml`)
- S'executa en cada push/PR a `develop` o `main`
- Executa tots els tests
- Genera report de cobertura
- Falla si algun test no passa

#### 2. **CD - Deploy** (`.github/workflows/cd.yml`)
- S'executa després que CI passi correctament
- Només desplegava a Render si els tests passen
- Només en branca `develop`

### Configurar Secrets a GitHub

Per que CI/CD funcioni correctament, configura aquests secrets:

1. Ves a **GitHub Repository** > **Settings** > **Secrets and variables** > **Actions**

2. Clica **New repository secret** i afegeix:

#### Secrets Obligatoris:

| Secret | Descripció | Com obtenir-lo |
|--------|------------|----------------|
| `RENDER_DEPLOY_HOOK_URL` | URL per triggerejar deploy | Render Dashboard > Service Settings > Deploy Hook |

#### Secrets Opcionals (per tests amb serveis reals):

| Secret | Descripció |
|--------|------------|
| `SECRET_KEY` | Django secret key per tests |
| `STRIPE_PUBLIC_KEY` | Stripe test public key |
| `STRIPE_SECRET_KEY` | Stripe test secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook secret |
| `SPOTIFY_CLIENT_ID` | Spotify test client ID |
| `SPOTIFY_CLIENT_SECRET` | Spotify test client secret |
| `GMAIL_USER` | Gmail per enviar emails test |
| `GMAIL_APP_PASSWORD` | Gmail app password |

**Nota:** Si no configures els secrets opcionals, GitHub Actions usarà valors dummy que permeten executar els tests sense errors.

### Obtenir Render Deploy Hook URL

1. Ves a [Render Dashboard](https://dashboard.render.com)
2. Selecciona el servei **dj-jukebox-dev**
3. Ves a **Settings** (icona engranatge)
4. Scroll down fins a **Deploy Hook**
5. Clica **Create Deploy Hook**
6. Copia la URL generada
7. Enganxa-la com a secret `RENDER_DEPLOY_HOOK_URL` a GitHub

## Estructura de Tests

```
jukebox/tests.py
├── SpotifyApiHelpersTests     # Tests per helpers Spotify
│   ├── test_camelot_from_key_string_supports_major_and_minor
│   └── test_pick_getsongbpm_match_prefers_title_and_artist_match
│
└── NotificationsTests          # Tests per sistema de notificacions
    ├── test_mark_notification_read_success
    ├── test_mark_notification_read_already_read
    └── ... (més tests de notificacions)
```

## Afegir Nous Tests

### Exemple de test per una view:

```python
from django.test import TestCase, Client
from django.urls import reverse

class SongListTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_song_list_requires_login(self):
        response = self.client.get(reverse('song_list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_song_list_shows_songs(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('song_list'))
        self.assertEqual(response.status_code, 200)
```

## Debugging Tests Fallits

### Ver logs detallats:

```bash
python manage.py test jukebox --verbosity=2
```

### Executar només el test que falla:

```bash
python manage.py test jukebox.tests.TestClassName.test_method_name
```

### Usar pdb (debugger):

```python
def test_something(self):
    import pdb; pdb.set_trace()  # Breakpoint
    # El teu codi de test...
```

## Best Practices

✅ **DO:**
- Escriu tests per cada nova feature
- Mantén els tests simples i enfocats
- Usa `setUp()` per preparar dades comunes
- Usa noms descriptius per als tests
- Executa els tests abans de fer commit

❌ **DON'T:**
- No facis tests que depenguin d'APIs externes (usa mocks)
- No facis tests que depenguin de l'ordre d'execució
- No facis tests massa llargs o complexos
- No commitejis codi amb tests fallits

## Recursos

- [Django Testing Documentation](https://docs.djangoproject.com/en/4.2/topics/testing/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
