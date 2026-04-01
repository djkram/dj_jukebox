# Fitxers de Traducció / Translation Files

Aquest directori conté els fitxers de traducció per a DJ Jukebox.

## Estructura

```
locale/
├── ca/                    # Català (Catalan)
│   └── LC_MESSAGES/
│       ├── django.po      # Fitxer de traducció editable
│       └── django.mo      # Fitxer compilat (auto-generat)
└── en/                    # Anglès (English)
    └── LC_MESSAGES/
        ├── django.po      # Translation file (editable)
        └── django.mo      # Compiled file (auto-generated)
```

## Fitxers .po vs .mo

- **`.po` (Portable Object)**: Fitxer de text editable amb les traduccions
- **`.mo` (Machine Object)**: Versió compilada del .po, utilitzada per Django (NO editar manualment)

## Com utilitzar

### 1. Editar traduccions

Obre els fitxers `.po` amb un editor de text o amb [Poedit](https://poedit.net/).

Exemple:
```po
msgid "Login"
msgstr "Entra"
```

- `msgid`: Text original (clau de traducció)
- `msgstr`: Traducció

### 2. Compilar traduccions

Després d'editar els fitxers `.po`, cal compilar-los:

```bash
python manage.py compilemessages
```

Això genera els fitxers `.mo` que Django utilitzarà.

### 3. Actualitzar traduccions

Quan s'afegeixen nous textos al codi, cal actualitzar els fitxers `.po`:

```bash
# Extreure nous textos i actualitzar fitxers .po
python manage.py makemessages -l ca
python manage.py makemessages -l en

# Compilar després de traduir
python manage.py compilemessages
```

## Workflow complet

```bash
# 1. Marcar textos nous amb {% trans %} o _() al codi
# 2. Extreure textos nous
python manage.py makemessages -l ca --no-obsolete
python manage.py makemessages -l en --no-obsolete

# 3. Editar locale/ca/LC_MESSAGES/django.po
# 4. Editar locale/en/LC_MESSAGES/django.po

# 5. Compilar
python manage.py compilemessages

# 6. Provar
python manage.py runserver
```

## Notes

- Els fitxers `.mo` són binaris i NO s'han d'editar manualment
- Els fitxers `.mo` es poden regenerar sempre que calgui
- Pots afegir `.mo` al `.gitignore` si vols (es regeneren automàticament)
- Usa `--no-obsolete` per eliminar traduccions obsoletes

## Estat actual

✅ Fitxers .po preparats amb més de 100 traduccions
✅ Cobreix: autenticació, navegació, festes, cançons, vots, coins, notificacions
⏳ Pendent: compilar amb `compilemessages` i implementar {% trans %} als templates

## Més informació

Consulta el fitxer `I18N_PLAN.md` a l'arrel del projecte per veure el pla complet d'implementació.
