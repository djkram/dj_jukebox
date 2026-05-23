# Pla d'Internacionalització (i18n) - DJ Jukebox

## Objectiu
Implementar suport multiidioma per català (ca) i anglès (en) utilitzant el sistema d'internacionalització de Django.

## Estructura de fitxers de traducció

```
dj_jukebox/
├── locale/
│   ├── ca/
│   │   └── LC_MESSAGES/
│   │       ├── django.po      # Traduccions Python/templates
│   │       └── django.mo      # Compilat (generat automàticament)
│   └── en/
│       └── LC_MESSAGES/
│           ├── django.po
│           └── django.mo
├── jukebox/
│   └── locale/
│       ├── ca/
│       │   └── LC_MESSAGES/
│       │       ├── django.po
│       │       └── django.mo
│       └── en/
│           └── LC_MESSAGES/
│               ├── django.po
│               └── django.mo
└── dj_jukebox/
    └── settings.py           # Configuració i18n
```

## Fase 1: Configuració de Django (settings.py)

### 1.1 Afegir configuració d'idiomes

```python
# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'ca'  # Idioma per defecte: català
TIME_ZONE = 'Europe/Madrid'  # o 'Europe/Andorra' per Catalunya
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [
    ('ca', 'Català'),
    ('en', 'English'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
    BASE_DIR / 'jukebox' / 'locale',
]
```

### 1.2 Afegir LocaleMiddleware

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # ← AFEGIR AQUÍ
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    # ...
]
```

### 1.3 Afegir context processor per l'idioma

```python
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'jukebox' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',  # ← AFEGIR
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'jukebox.context_processors.selected_party',
                'jukebox.context_processors.user_avatar',
                'jukebox.context_processors.unread_notifications_count',
            ],
        },
    },
]
```

## Fase 2: Afegir URLs per canvi d'idioma

### 2.1 Actualitzar dj_jukebox/urls.py

```python
from django.conf.urls.i18n import i18n_patterns
from django.urls import path, include

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),  # Endpoint per canviar idioma
]

urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('jukebox.urls')),
)
```

## Fase 3: Marcar textos per traduir en templates

### 3.1 Carregar templatetags d'i18n

A cada template que contingui text, afegir al principi:

```django
{% load i18n %}
```

### 3.2 Marcar textos per traducció

**Textos simples:**
```django
{% trans "Login" %}
{% trans "Has oblidat la contrasenya?" %}
{% trans "Perfil" %}
{% trans "Sortir" %}
```

**Textos amb variables:**
```django
{% blocktrans with votes=votes_left %}
Tens {{ votes }} vots disponibles
{% endblocktrans %}
```

**Textos amb HTML:**
```django
{% blocktrans %}
<strong>Benvingut</strong> de nou
{% endblocktrans %}
```

### 3.3 Exemples de fitxers a actualitzar

**jukebox/templates/account/login.html:**
```django
{% load i18n %}

<h1>{% trans "Login" %}</h1>
<a href="{% url 'account_reset_password' %}">{% trans "Has oblidat la contrasenya?" %}</a>
<button type="submit">{% trans "Entra" %}</button>
```

**jukebox/templates/jukebox/admin_base.html:**
```django
{% load i18n %}

<a class="dropdown-item" href="{% url 'profile' %}">
    <i class="fas fa-user"></i>
    {% trans "Perfil" %}
</a>

<button type="submit" class="dropdown-item">
    <i class="fas fa-sign-out-alt"></i>
    {% trans "Sortir" %}
</button>
```

## Fase 4: Marcar textos en codi Python (views, models, forms)

### 4.1 Importar funcions de traducció

```python
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext as _t
```

### 4.2 Exemple en models.py

```python
class Party(models.Model):
    name = models.CharField(
        max_length=200,
        verbose_name=_("Nom de la festa")
    )

    class Meta:
        verbose_name = _("Festa")
        verbose_name_plural = _("Festes")
```

### 4.3 Exemple en views.py

```python
from django.utils.translation import gettext as _
from django.contrib import messages

def some_view(request):
    messages.success(request, _("Operació completada amb èxit"))
    return render(request, 'template.html', {
        'title': _("Títol de la pàgina")
    })
```

### 4.4 Exemple en forms.py

```python
from django.utils.translation import gettext_lazy as _

class PartyForm(forms.ModelForm):
    name = forms.CharField(
        label=_("Nom de la festa"),
        help_text=_("Introdueix el nom de l'esdeveniment")
    )
```

## Fase 5: Generar fitxers de traducció

### 5.1 Crear directoris

```bash
# Des de la carpeta arrel del projecte
mkdir -p locale/ca/LC_MESSAGES
mkdir -p locale/en/LC_MESSAGES
mkdir -p jukebox/locale/ca/LC_MESSAGES
mkdir -p jukebox/locale/en/LC_MESSAGES
```

### 5.2 Extreure textos per traduir

```bash
# Generar fitxers .po per l'aplicació principal
python manage.py makemessages -l ca
python manage.py makemessages -l en

# Generar per l'app jukebox
cd jukebox
django-admin makemessages -l ca
django-admin makemessages -l en
cd ..
```

### 5.3 Exemple de fitxer django.po

**locale/ca/LC_MESSAGES/django.po:**
```po
# LANGUAGE: Català
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"
"Language: ca\n"

msgid "Login"
msgstr "Entra"

msgid "Has oblidat la contrasenya?"
msgstr "Has oblidat la contrasenya?"

msgid "Perfil"
msgstr "Perfil"

msgid "Sortir"
msgstr "Sortir"

#: jukebox/templates/jukebox/song_list.html:456
msgid "Disponibles"
msgstr "Disponibles"
```

**locale/en/LC_MESSAGES/django.po:**
```po
# LANGUAGE: English
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"
"Language: en\n"

msgid "Login"
msgstr "Login"

msgid "Has oblidat la contrasenya?"
msgstr "Forgot your password?"

msgid "Perfil"
msgstr "Profile"

msgid "Sortir"
msgstr "Logout"

#: jukebox/templates/jukebox/song_list.html:456
msgid "Disponibles"
msgstr "Available"
```

### 5.4 Compilar traduccions

```bash
python manage.py compilemessages
```

## Fase 6: Afegir selector d'idioma a la UI

### 6.1 Crear template per selector d'idioma

**jukebox/templates/jukebox/language_selector.html:**
```django
{% load i18n %}

<div class="language-selector">
  <form action="{% url 'set_language' %}" method="post">
    {% csrf_token %}
    <input name="next" type="hidden" value="{{ redirect_to }}">
    <select name="language" onchange="this.form.submit()">
      {% get_current_language as LANGUAGE_CODE %}
      {% get_available_languages as LANGUAGES %}
      {% for lang_code, lang_name in LANGUAGES %}
        <option value="{{ lang_code }}" {% if lang_code == LANGUAGE_CODE %}selected{% endif %}>
          {{ lang_name }}
        </option>
      {% endfor %}
    </select>
  </form>
</div>
```

### 6.2 Incloure selector a admin_base.html

```django
{% load i18n %}

<nav class="topbar">
  <!-- ... altres elements ... -->

  <!-- Selector d'idioma -->
  <div class="language-selector-container">
    {% include "jukebox/language_selector.html" %}
  </div>
</nav>
```

## Fase 7: Estils per selector d'idioma

### 7.1 CSS per desktop (Sonic Architect)

```css
@media (min-width: 768px) {
  .language-selector-container {
    margin-left: 1rem;
  }

  .language-selector select {
    background: #f1f4f7;
    border: 2px solid transparent;
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
    font-weight: 600;
    color: #181c1e;
    cursor: pointer;
    transition: all 200ms;
  }

  .language-selector select:hover {
    border-color: #0040e0;
    background: #ffffff;
  }

  .language-selector select:focus {
    outline: none;
    border-color: #0040e0;
    box-shadow: 0 0 0 4px rgba(0,64,224,0.1);
  }
}
```

### 7.2 CSS per mobile (Tailwind)

```css
@media (max-width: 767px) {
  .language-selector {
    width: 100%;
  }

  .language-selector select {
    width: 100%;
    background: white;
    border: 1px solid #c4c5d9;
    border-radius: 0.75rem;
    padding: 0.625rem 0.875rem;
    font-size: 0.875rem;
    font-weight: 600;
    color: #191c1f;
  }
}
```

## Fase 8: Actualitzar allauth per traduccions

### 8.1 Configurar idioma per allauth

Django-allauth ja té suport per múltiples idiomes. Només cal assegurar que estigui configurat correctament:

```python
# settings.py
ACCOUNT_EMAIL_SUBJECT_PREFIX = _("DJ Jukebox - ")
```

### 8.2 Sobrescriure emails d'allauth (opcional)

Si vols personalitzar els emails de verificació, crea:

```
jukebox/templates/account/email/
├── email_confirmation_subject.txt
├── email_confirmation_message.txt
├── password_reset_key_subject.txt
└── password_reset_key_message.txt
```

## Prioritat de textos a traduir

### 1. Alta prioritat (pàgines públiques)
- ✅ login.html
- ✅ signup.html
- ✅ password_reset.html
- ✅ password_reset_done.html
- ✅ password_reset_from_key.html
- ✅ password_reset_from_key_done.html
- ✅ email_confirm.html
- ✅ verification_sent.html

### 2. Mitja prioritat (pàgines autenticades)
- song_list.html (cançons, maleta DJ, sessió)
- select_party.html (seleccionar festa)
- buy_votes.html (comprar coins/vots)
- profile.html (perfil usuari)
- notifications.html (notificacions)

### 3. Baixa prioritat (admin/DJ)
- admin_base.html (navbar, sidebar)
- dj_dashboard.html (dashboard DJ)
- dj_backoffice.html (backoffice)
- party_settings.html (configuració festa)
- manage_song_requests.html (peticions)

### 4. Models i missatges del sistema
- models.py (verbose_name)
- forms.py (labels, help_text)
- views.py (missatges d'error/èxit)
- notifications.py (títols, missatges)

## Workflow de treball

1. **Actualitzar settings.py** amb configuració i18n
2. **Afegir LocaleMiddleware** a MIDDLEWARE
3. **Crear directoris** locale/
4. **Marcar textos** en templates amb {% trans %}
5. **Executar makemessages** per generar .po
6. **Traduir** fitxers .po manualment
7. **Compilar** amb compilemessages
8. **Provar** canviant d'idioma
9. **Iterar** afegint més textos

## Comandes útils

```bash
# Generar traduccions
python manage.py makemessages -l ca
python manage.py makemessages -l en

# Actualitzar traduccions existents
python manage.py makemessages -l ca --no-obsolete
python manage.py makemessages -l en --no-obsolete

# Compilar traduccions
python manage.py compilemessages

# Netejar traduccions obsoletes
python manage.py makemessages -l ca --no-obsolete
python manage.py makemessages -l en --no-obsolete

# Traduir només JavaScript (si cal)
python manage.py makemessages -d djangojs -l ca
python manage.py makemessages -d djangojs -l en
```

## Notes importants

1. **gettext vs gettext_lazy:**
   - `gettext` (_t): per textos que s'avaluen immediatament (dins funcions)
   - `gettext_lazy` (_): per textos que s'avaluen més tard (definicions de classe, models)

2. **Singular vs Plural:**
   ```python
   from django.utils.translation import ngettext

   count = 5
   message = ngettext(
       'Tens %(count)d vot disponible',
       'Tens %(count)d vots disponibles',
       count
   ) % {'count': count}
   ```

3. **Context per traduccions ambigües:**
   ```python
   from django.utils.translation import pgettext

   # "play" pot ser "reproduir" o "jugar"
   play_music = pgettext("music", "play")  # "reproduir"
   play_game = pgettext("game", "play")    # "jugar"
   ```

4. **Format de dates i números:**
   Django formata automàticament segons l'idioma si USE_L10N = True

5. **Mantenir coherència:**
   - Crear un glossari de termes (Coins, Vots, Festa, DJ, etc.)
   - Revisar traduccions amb nadius
   - Usar la mateixa terminologia arreu

## Glossari de termes clau

| Català | English | Context |
|--------|---------|---------|
| Entra | Login | Botó accés |
| Sortir | Logout | Botó sortir |
| Registra't | Sign up | Botó registre |
| Perfil | Profile | Pàgina usuari |
| Festa | Party | Esdeveniment |
| Cançó | Song | Tema musical |
| Vot | Vote | Votació |
| Coin | Coin | Moneda virtual |
| Maleta del DJ | DJ Bag | Cançons pendents |
| Sessió | Session | Cançons reproduïdes |
| Petició | Request | Sol·licitud cançó |
| Notificació | Notification | Avís sistema |
| Disponibles | Available | Vots restants |
| Comprar | Buy | Adquirir |
| Connectar | Connect | Enllaçar compte |
| Reproduir | Play | Tocar música |
| Acceptar | Accept | Aprovar |
| Rebutjar | Reject | Denegar |

## Proves a fer

- [ ] Canviar idioma des del selector
- [ ] Verificar que tots els textos canvien
- [ ] Comprovar emails en ambdós idiomes
- [ ] Provar formularis (errors en ambdós idiomes)
- [ ] Verificar notificacions
- [ ] Revisar textos en versió desktop i mobile
- [ ] Comprovar que l'idioma es manté entre pàgines
- [ ] Verificar format de dates i números

## Recursos

- [Django i18n documentation](https://docs.djangoproject.com/en/5.2/topics/i18n/)
- [Django translation tutorial](https://docs.djangoproject.com/en/5.2/topics/i18n/translation/)
- [PO file format](https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html)
- [Poedit](https://poedit.net/) - Editor gràfic per fitxers .po
