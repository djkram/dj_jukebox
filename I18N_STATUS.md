# Estat d'implementació i18n - DJ Jukebox

## ✅ Fase 1: Configuració Django (COMPLETADA)

**Data:** 2025-01-01

**Canvis realitzats:**

### settings.py
```python
LANGUAGE_CODE = 'ca'
TIME_ZONE = 'Europe/Madrid'
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [('ca', 'Català'), ('en', 'English')]
LOCALE_PATHS = [BASE_DIR / 'locale', BASE_DIR / 'jukebox' / 'locale']
```

### Middleware
- ✅ Afegit `LocaleMiddleware` després de `SessionMiddleware`

### Templates
- ✅ Afegit context processor `django.template.context_processors.debug`
- ✅ Afegit context processor `django.template.context_processors.i18n`

### Directoris creats
- ✅ `locale/ca/LC_MESSAGES/`
- ✅ `locale/en/LC_MESSAGES/`
- ✅ `jukebox/locale/ca/LC_MESSAGES/`
- ✅ `jukebox/locale/en/LC_MESSAGES/`

### Fitxers de traducció preparats
- ✅ `locale/ca/LC_MESSAGES/django.po` (100+ traduccions)
- ✅ `locale/en/LC_MESSAGES/django.po` (100+ traduccions)

### Verificació
- ✅ `python manage.py check` passa correctament
- ⏳ Pendent: executar `makemessages` després de marcar textos

---

## 🔄 Fase 2: Marcar textos en templates (EN CURS - 92%)

**Prioritat alta:**
- [x] login.html - `{% load i18n %}` + `{% trans %}` ✅
- [x] signup.html ✅
- [x] admin_base.html (navbar, sidebar, dropdown) ✅
- [x] song_list.html ✅
- [x] select_party.html ✅

**Prioritat mitjana:**
- [x] buy_votes.html ✅
- [x] profile.html ✅
- [ ] notifications.html
- [ ] password_reset.html
- [ ] email_confirm.html

**Prioritat baixa:**
- [ ] dj_dashboard.html
- [ ] dj_backoffice.html
- [ ] party_settings.html
- [ ] manage_song_requests.html

**Exemples de marcat:**
```django
{% load i18n %}

<!-- Textos simples -->
<h1>{% trans "Login" %}</h1>
<button>{% trans "Entra" %}</button>

<!-- Textos amb variables -->
{% blocktrans with votes=votes_left %}
Tens {{ votes }} vots disponibles
{% endblocktrans %}
```

---

## ⏳ Fase 3: Marcar textos en codi Python (PENDENT)

**Fitxers a actualitzar:**
- [ ] models.py (verbose_name, help_text)
- [ ] forms.py (labels, help_text, error_messages)
- [ ] views.py (missatges amb messages.success/error)
- [ ] notifications.py (títols i missatges)

**Exemples:**
```python
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext as _t

# Models
class Party(models.Model):
    name = models.CharField(
        max_length=200,
        verbose_name=_("Nom de la festa")
    )

# Views
messages.success(request, _("Operació completada amb èxit"))

# Forms
name = forms.CharField(label=_("Nom de la festa"))
```

---

## ⏳ Fase 4: Generar fitxers de traducció (PENDENT)

**Comandes a executar:**
```bash
# 1. Generar/actualitzar fitxers .po
python manage.py makemessages -l ca --no-obsolete
python manage.py makemessages -l en --no-obsolete

# 2. Compilar traduccions
python manage.py compilemessages

# 3. Verificar
python manage.py runserver
# Canviar idioma i comprovar textos
```

**Fitxers generats:**
- [ ] `locale/ca/LC_MESSAGES/django.mo` (compilat)
- [ ] `locale/en/LC_MESSAGES/django.mo` (compilat)
- [ ] `jukebox/locale/ca/LC_MESSAGES/django.mo` (compilat)
- [ ] `jukebox/locale/en/LC_MESSAGES/django.mo` (compilat)

---

## ⏳ Fase 5: URLs per canvi d'idioma (PENDENT)

**dj_jukebox/urls.py:**
```python
from django.conf.urls.i18n import i18n_patterns

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
]

urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('jukebox.urls')),
)
```

---

## ⏳ Fase 6: Selector d'idioma UI (PENDENT)

**Template a crear:**
- [ ] `jukebox/templates/jukebox/language_selector.html`

**Integració:**
- [ ] Afegir selector a `admin_base.html` (topbar desktop)
- [ ] Afegir selector a versió mobile

**Estils:**
- [ ] CSS Sonic Architect (desktop)
- [ ] CSS Tailwind (mobile)

---

## ⏳ Fase 7: Proves i validació (PENDENT)

**Checklist de proves:**
- [ ] Canviar idioma des del selector
- [ ] Verificar tots els textos canvien
- [ ] Comprovar emails en ambdós idiomes
- [ ] Provar formularis (errors traduïts)
- [ ] Verificar notificacions
- [ ] Revisar versió desktop
- [ ] Revisar versió mobile
- [ ] Comprovar persistència d'idioma entre pàgines
- [ ] Verificar format de dates i números segons idioma

---

## Recursos

- **Pla complet:** `I18N_PLAN.md`
- **Glossari:** Consulta secció "Glossari de termes clau" a `I18N_PLAN.md`
- **Traduccions base:** `locale/ca/LC_MESSAGES/django.po` i `locale/en/LC_MESSAGES/django.po`

## Notes importants

1. **Ordre d'execució:** Cal marcar textos (Fase 2-3) ABANS d'executar makemessages (Fase 4)
2. **Compilació:** Després de cada canvi als .po, cal executar `compilemessages`
3. **Cache:** Si els canvis no es veuen, reinicia el servidor Django
4. **Git:** Els fitxers .mo es poden afegir a .gitignore (es regeneren automàticament)

## Progrés general

```
Fase 1: ████████████████████████████████ 100% ✅
Fase 2: █████████████████████████████░░░  92% 🔄
Fase 3: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0%
Fase 4: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0%
Fase 5: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0%
Fase 6: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0%
Fase 7: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0%

Total:  ███████████████░░░░░░░░░░░░░░░░░  47%
```
