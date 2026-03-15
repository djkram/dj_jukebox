# Configuració Google OAuth

## 1. Crear un projecte a Google Cloud Console

1. Ves a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nou projecte o selecciona un existent
3. Nom del projecte: "DJ Jukebox" (o el que prefereixis)

## 2. Habilitar Google+ API

1. Al menú lateral, ves a **APIs & Services** → **Library**
2. Cerca "Google+ API"
3. Fes clic i selecciona **Enable**

## 3. Configurar pantalla de consentiment OAuth

1. Ves a **APIs & Services** → **OAuth consent screen**
2. Selecciona **External** (o Internal si és per una organització)
3. Omple la informació:
   - **App name**: DJ Jukebox
   - **User support email**: el teu email
   - **Developer contact information**: el teu email
4. Fes clic a **Save and Continue**
5. A **Scopes**, no cal afegir res (els scopes bàsics ja estan inclosos)
6. Fes clic a **Save and Continue**
7. A **Test users** (si és External en mode testing):
   - Afegeix els emails dels usuaris que vols que puguin fer login mentre l'app està en mode testing
8. Fes clic a **Save and Continue**

## 4. Crear credencials OAuth 2.0

1. Ves a **APIs & Services** → **Credentials**
2. Fes clic a **+ CREATE CREDENTIALS** → **OAuth client ID**
3. Tipus d'aplicació: **Web application**
4. Nom: "DJ Jukebox Web"
5. **Authorized JavaScript origins**:
   - Desenvolupament: `http://localhost:8000` i `http://127.0.0.1:8000`
   - Producció: `https://el-teu-domini.com`
6. **Authorized redirect URIs**:
   - Desenvolupament: `http://localhost:8000/accounts/google/login/callback/` i `http://127.0.0.1:8000/accounts/google/login/callback/`
   - Producció: `https://el-teu-domini.com/accounts/google/login/callback/`
7. Fes clic a **CREATE**

## 5. Copiar les credencials

1. Google et mostrarà el **Client ID** i **Client Secret**
2. Copia'ls i afegeix-los al fitxer `.env`:

```bash
GOOGLE_CLIENT_ID=el-teu-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=el-teu-client-secret
```

## 6. Aplicar les migracions

```bash
python manage.py migrate
```

## 7. Afegir el provider a la base de dades (Django Admin)

1. Executa el servidor: `python manage.py runserver`
2. Ves a http://localhost:8000/admin/
3. A **Sites** → **Sites**, assegura't que el domini sigui correcte:
   - Development: `127.0.0.1:8000`
   - Production: `el-teu-domini.com`
4. A **Social accounts** → **Social applications**, fes clic a **Add**:
   - **Provider**: Google
   - **Name**: Google
   - **Client id**: el teu GOOGLE_CLIENT_ID
   - **Secret key**: el teu GOOGLE_CLIENT_SECRET
   - **Sites**: Selecciona el teu site (127.0.0.1:8000 o el teu domini)
5. Guarda

## 8. Provar el login

1. Ves a http://localhost:8000/accounts/login/
2. Fes clic a **Connecta't amb Google**
3. Hauràs de veure la pantalla de consentiment de Google

## Notes

- Si l'app està en mode **Testing**, només els usuaris que hagis afegit a "Test users" podran fer login
- Per publicar l'app i permetre que qualsevol persona amb compte Google faci login, has de:
  1. Anar a **OAuth consent screen**
  2. Clicar **PUBLISH APP**
  3. Google revisarà l'app (pot trigar uns dies)

- Els scopes configurats són:
  - `profile`: Per obtenir el nom i foto de perfil
  - `email`: Per obtenir l'email de l'usuari
