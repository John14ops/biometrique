# Déploiement — Backend Railway + Frontend Vercel

Guide complet du dev local au prod en ligne.

```
┌─────────────────┐         HTTPS         ┌──────────────────┐
│  Vercel (CDN)   │ ─────────────────────▶│  Railway          │
│  React/Vite     │                       │  api + worker     │
│  apps/dashboard │                       │  + Redis (plugin) │
└─────────────────┘                       └────────┬─────────┘
                                                    │
                                                    ▼
                                          ┌──────────────────┐
                                          │     Supabase     │
                                          │  Postgres pgvec  │
                                          └──────────────────┘
```

Tout se fait depuis l'interface web (pas de CLI requis — la connexion GitHub se fait par OAuth navigateur de toute façon).

---

## 1 · Backend sur Railway

### 1.1 — Créer le projet

1. Va sur **railway.app** → connecte-toi avec GitHub (autorise l'accès au repo `Skwiz-blip/Reconnaissance-Faciale-V0`).
2. **New Project → Deploy from GitHub repo** → sélectionne ce repo.
3. Railway va créer un premier service. Renomme-le **`api`**.

### 1.2 — Configurer le service `api`

Dans **Settings** du service `api` :

| Champ | Valeur |
|---|---|
| Root Directory | `biometric-system` |
| Builder | Dockerfile (auto-détecté via `railway.json` → `infra/docker/Dockerfile.api`) |
| Healthcheck Path | `/health` (déjà dans `railway.json`) |

Dans **Settings → Networking** : clique **Generate Domain** pour obtenir une URL publique (`https://api-xxxx.up.railway.app`).

### 1.3 — Ajouter Redis

Dans le projet Railway : **New → Database → Add Redis**. Railway crée un plugin Redis et expose une variable `REDIS_URL` automatiquement.

### 1.4 — Variables d'environnement du service `api`

**Settings → Variables**, ajoute (valeurs depuis ton `.env` local) :

```
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...
SECRET_KEY=...                          # génère: python -c "import secrets;print(secrets.token_hex(32))"
APP_ENV=production
DEBUG=false
REDIS_URL=${{Redis.REDIS_URL}}          # référence le plugin Redis créé à l'étape 1.3
EMBEDDING_ENCRYPTION_ENABLED=false
CORS_ORIGINS=                           # à remplir après l'étape 2 (URL Vercel)
PORT=8000
```

Railway injecte aussi `PORT` automatiquement — vérifie que `Dockerfile.api` écoute bien sur `0.0.0.0:8000` (déjà le cas).

### 1.5 — Déployer

Le push sur `main` déclenche un build automatique. Premier build : ~8-10 min (mêmes dépendances que le build Docker local). Suis les logs dans l'onglet **Deployments**.

Une fois déployé :
```powershell
curl https://api-xxxx.up.railway.app/health
```

### 1.6 — Ajouter le service `worker` (Celery)

1. Dans le même projet Railway : **New → GitHub Repo** → sélectionne à nouveau le même repo.
2. Renomme ce service **`worker`**.
3. **Settings** :
   - Root Directory : `biometric-system`
   - Builder : Dockerfile (même `infra/docker/Dockerfile.api`)
   - **Custom Start Command** : `celery -A tasks worker --loglevel=info --concurrency=2`
   - Désactive le Healthcheck Path (laisse vide — ce service n'expose pas de port HTTP)
   - Pas besoin de **Generate Domain** (le worker n'est pas exposé publiquement)
4. **Variables** : copie les mêmes variables que le service `api` (étape 1.4).

### 1.7 — CORS pour Vercel

Une fois ton URL Vercel connue (étape 2.3), reviens dans **Variables** du service `api` et mets à jour :

```
CORS_ORIGINS=https://reconnaissance-faciale-v0.vercel.app,https://*.vercel.app
```

Le service redémarre automatiquement.

---

## 2 · Frontend sur Vercel

### 2.1 — Configurer le projet

Sur **vercel.com → ton projet → Settings → General** :

| Champ | Valeur |
|---|---|
| Root Directory | `biometric-system/apps/dashboard` |
| Framework Preset | Vite (détecté auto via `vercel.json`) |
| Build Command | `npm run build` (auto) |
| Output Directory | `dist` (auto) |
| Install Command | `npm install` (auto) |

### 2.2 — Variables d'environnement

**Settings → Environment Variables** :

| Nom | Valeur | Scope |
|---|---|---|
| `VITE_API_URL` | `https://api-xxxx.up.railway.app/` | Production, Preview |

⚠️ Le `/` final est important.

### 2.3 — Déployer

Push sur `main` → Vercel build automatiquement.

Ou en CLI (déjà installé sur cette machine) :
```powershell
cd biometric-system\apps\dashboard
vercel --prod
```

URL : `https://reconnaissance-faciale-v0.vercel.app` (ou ton nom de projet)

### 2.4 — Revenir mettre à jour CORS côté backend

Ajoute l'URL exacte de Vercel dans les variables Railway (étape 1.7).

---

## 3 · Vérifications finales

```powershell
# Backend healthy ?
curl https://api-xxxx.up.railway.app/health

# Dashboard répond ?
curl -I https://reconnaissance-faciale-v0.vercel.app

# Le dashboard arrive à parler à l'API ?
# → Ouvre l'app dans le navigateur, "Créer le premier compte"
# → DevTools Network, regarde l'appel /api/v1/auth/register
# → Doit retourner 201 et stocker access_token
```

---

## 4 · Notes Railway utiles

- **Logs en temps réel** : onglet **Deployments → View Logs** sur chaque service.
- **Redéployer** : push sur `main`, ou bouton **Redeploy** dans Deployments.
- **Scale** : Settings → Resources (vCPU/RAM par service).
- **Coût** : Railway facture à l'usage (pas de tier gratuit permanent comme avant) — un service api+worker+redis légers tourne typiquement autour de 5-10 $/mois selon le trafic. Surveille l'usage dans **Project → Usage**.

---

## 5 · Migrations SQL en prod

Toutes les migrations doivent être exécutées **manuellement** dans le SQL Editor Supabase (dans l'ordre `001` → `005`) avant le premier déploiement du backend, sinon l'API plantera au boot. (Déjà fait pour cet environnement — 29 tables/vues vérifiées.)

---

## 6 · Troubleshooting

| Symptôme | Cause probable | Fix |
|---|---|---|
| Build "Out of memory" | Plan Railway trop petit | Augmenter les ressources du service dans Settings → Resources |
| `relation "X" does not exist` | Migration SQL manquante | Exécuter `00X_*.sql` sur Supabase |
| `CORS error` côté dashboard | Origine pas dans `CORS_ORIGINS` | Voir étape 1.7 |
| 502 sur `/api/*` | Backend down ou redéploie en cours | Voir logs du service `api` |
| Worker ne traite aucune tâche | `REDIS_URL` pas identique entre `api` et `worker` | Vérifier que les deux services référencent `${{Redis.REDIS_URL}}` |
| Endpoints `/voice/*` ou `/affect/*` retournent 500 | Build avec `requirements-minimal.txt` (Phase 6 voice/affect exclu) | Normal pour l'instant — passer sur `requirements.txt` complet plus tard si besoin |
