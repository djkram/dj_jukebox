# Tests DJ Jukebox

Estructura modular de tests per DJ Jukebox amb cobertura completa de funcionalitats.

## Estructura

```
jukebox/tests/
├── __init__.py                  # Mòdul de tests
├── README.md                    # Aquesta documentació
├── test_models.py               # Tests unitaris per models
├── test_views.py                # Tests d'integració per views
├── test_votes.py                # Tests per sistema de votes/coins
├── test_spotify_api.py          # Tests per helpers de Spotify
├── test_notifications.py        # Tests per notificacions
└── test_integration.py          # Tests end-to-end complets
```

## Tipus de Tests

### 🔬 Tests Unitaris (test_models.py)

Testen models individuals aïlladament:
- **UserModelTests**: Creació usuaris, credits
- **PartyModelTests**: Creació festes, generació de codis
- **PlaylistModelTests**: Playlists de Spotify
- **SongModelTests**: Cançons amb metadata (BPM, key)
- **VoteModelTests**: Sistema de votació
- **VotePackageModelTests**: Paquets de vots comprats
- **PartyCoinsGrantModelTests**: Grants de coins gratuïts
- **SongRequestModelTests**: Peticions de cançons
- **NotificationModelTests**: Notificacions

**Executar:**
```bash
python manage.py test jukebox.tests.test_models
```

### 🧪 Tests de Sistema (test_votes.py)

Testen la lògica de negoci del sistema de votes/coins:
- **VotesSystemTests**: Càlcul de vots disponibles
- **CoinsSystemTests**: Gestió de coins globals i per festa
- **ConversionRatesTests**: Conversions coins → votes amb bonificacions
- **VotesAndCoinsIntegrationTests**: Workflow complet

**Executar:**
```bash
python manage.py test jukebox.tests.test_votes
```

### 🌐 Tests d'Integració (test_views.py)

Testen views amb requests HTTP reals:
- **SelectPartyViewTests**: Selecció de festa
- **SongListViewTests**: Llista de cançons ordenada per vots
- **VoteViewTests**: Votació de cançons
- **BuyVotesViewTests**: Conversió coins → votes
- **SongRequestViewTests**: Peticions de cançons
- **DJDashboardViewTests**: Dashboard del DJ
- **DJBackofficeViewTests**: Backoffice gestió festes

**Executar:**
```bash
python manage.py test jukebox.tests.test_views
```

### 🔗 Tests End-to-End (test_integration.py)

Testen workflows complets d'usuari:
- **UserJourneyTests**: Journey complet usuari (login → votar)
- **DJWorkflowTests**: Workflow DJ (crear festa → gestionar)
- **NotificationWorkflowTests**: Sistema de notificacions complet
- **MultiPartyTests**: Múltiples festes simultànies

**Executar:**
```bash
python manage.py test jukebox.tests.test_integration
```

### 🎵 Tests API (test_spotify_api.py)

Testen helpers de Spotify API (sense calls reals):
- **SpotifyApiHelpersTests**: Conversió keys Camelot, matching BPM

**Executar:**
```bash
python manage.py test jukebox.tests.test_spotify_api
```

### 🔔 Tests Notificacions (test_notifications.py)

Testen sistema de notificacions i auto-sync:
- **NotificationsTests**: Marcar llegides, permisos
- **AutoSyncTests**: Auto-sincronització playlists

**Executar:**
```bash
python manage.py test jukebox.tests.test_notifications
```

## Executar Tests

### Tots els tests
```bash
python manage.py test jukebox.tests
```

### Un mòdul específic
```bash
python manage.py test jukebox.tests.test_models
```

### Una classe específica
```bash
python manage.py test jukebox.tests.test_models.UserModelTests
```

### Un test específic
```bash
python manage.py test jukebox.tests.test_models.UserModelTests.test_user_creation
```

### Amb verbosity
```bash
python manage.py test jukebox.tests --verbosity=2
```

## Cobertura

### Generar report de cobertura
```bash
coverage run --source='jukebox' manage.py test jukebox.tests
coverage report
coverage html
open htmlcov/index.html
```

### Objectius de cobertura
- **Models**: >90% cobertura
- **Views**: >80% cobertura
- **Business logic (votes.py)**: >95% cobertura
- **Global**: >85% cobertura

## Convencions

### Nomenclatura
- Tests unitaris: `test_<funcionalitat>`
- Tests d'integració: `test_<workflow>`
- Setup: `setUp()` per preparar dades comunes

### Estructura d'un test
```python
def test_feature_description(self):
    """Descripció clara del que testa"""
    # Arrange (preparar dades)
    user = User.objects.create_user(...)

    # Act (executar acció)
    result = some_function(user)

    # Assert (verificar resultat)
    self.assertEqual(result, expected)
```

### Asserts comuns
- `assertEqual(a, b)`: a == b
- `assertTrue(x)`: x és True
- `assertFalse(x)`: x és False
- `assertIn(item, list)`: item està a list
- `assertContains(response, text)`: response conté text
- `assertRaises(Exception)`: s'ha llençat excepció

## Dades de Test

### Fixtures
No utilitzem fixtures per mantenir tests independents.
Cada test crea les seves pròpies dades al `setUp()`.

### Factories (futur)
Considerar factory_boy per generar dades de test més fàcilment:
```python
user = UserFactory(credits=100)
party = PartyFactory(owner=user)
```

## CI/CD

Els tests s'executen automàticament a GitHub Actions:
- ✅ En cada push a `develop` o `main`
- ✅ En cada Pull Request
- ✅ Abans de fer deploy a Render

Si els tests fallen, el deploy es cancel·la automàticament.

## Debug

### Veure SQL queries
```python
from django.test.utils import override_settings

@override_settings(DEBUG=True)
def test_something(self):
    from django.db import connection
    # ... test code ...
    print(connection.queries)
```

### Usar pdb
```python
def test_something(self):
    import pdb; pdb.set_trace()
    # ... test code ...
```

### Print output
```bash
python manage.py test jukebox.tests --debug-mode
```

## Afegir Nous Tests

### 1. Identificar què testar
- Nova funcionalitat? → Test unitari + integració
- Nova view? → Test d'integració
- Bug fix? → Test de regressió

### 2. Escollir fitxer
- Model? → `test_models.py`
- View? → `test_views.py`
- Lògica votes? → `test_votes.py`
- Workflow complet? → `test_integration.py`

### 3. Seguir estructura
```python
class NewFeatureTests(TestCase):
    """Tests per la nova funcionalitat X"""

    def setUp(self):
        # Preparar dades comunes
        pass

    def test_feature_success_case(self):
        """Test cas d'èxit"""
        pass

    def test_feature_error_case(self):
        """Test cas d'error"""
        pass
```

## Recursos

- [Django Testing Docs](https://docs.djangoproject.com/en/4.2/topics/testing/)
- [Python unittest Docs](https://docs.python.org/3/library/unittest.html)
- [Coverage.py Docs](https://coverage.readthedocs.io/)

## Manteniment

- ✅ Mantenir tests actualitzats amb canvis de codi
- ✅ Refactoritzar tests quan es refactoritza codi
- ✅ Eliminar tests obsolets
- ✅ Afegir tests per cada bug trobat
- ✅ Revisar cobertura regularment
