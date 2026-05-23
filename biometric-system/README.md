# Biometric Recognition System

Système IA de reconnaissance faciale biométrique professionnel.
**Phase 1** — Pipeline core + API FastAPI + Supabase (pgvector)

---

## 🚀 Démarrage rapide

### 1. Prérequis
- Python 3.11+
- Docker & Docker Compose
- Compte Supabase (déjà configuré)

### 2. Configuration
```bash
cp .env.example .env
# Éditer .env et ajouter ta SUPABASE_SERVICE_KEY
# (Settings > API > service_role dans le dashboard Supabase)
```

### 3. Base de données Supabase
Dans le **SQL Editor** de ton dashboard Supabase, exécuter :
```
supabase/migrations/001_initial_schema.sql
```
Cela crée toutes les tables + index pgvector + fonctions RPC.

### 4. Installation Python
```bash
pip install -r requirements.txt
```

### 5. Lancer l'API
```bash
cd services/api-gateway
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Ou via Docker
```bash
docker compose up --build
```

---

## 📡 API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/recognize` | Reconnaissance base64 |
| POST | `/api/v1/recognize/upload` | Reconnaissance upload |
| POST | `/api/v1/identities` | Créer identité |
| GET  | `/api/v1/identities` | Lister identités |
| POST | `/api/v1/identities/{id}/enroll` | Enrôler visage |
| GET  | `/api/v1/unknowns` | Visages inconnus |
| POST | `/api/v1/unknowns/{id}/resolve` | Résoudre inconnu |
| WS   | `/ws/camera/{camera_id}` | Flux temps réel |
| GET  | `/health` | Santé système |
| GET  | `/api/v1/stats` | Statistiques |
| GET  | `/docs` | Swagger UI |

---

## 🔧 Test rapide

```bash
# Créer une identité
curl -X POST http://localhost:8000/api/v1/identities \
  -H "Content-Type: application/json" \
  -d '{"full_name": "Louis Dupont", "email": "louis@example.com", "role": "user"}'

# Enrôler un visage (remplacer BASE64_IMAGE)
curl -X POST http://localhost:8000/api/v1/identities/{id}/enroll/upload \
  -F "file=@photo.jpg"

# Reconnaissance
curl -X POST http://localhost:8000/api/v1/recognize/upload \
  -F "file=@test.jpg" \
  -F "check_liveness=false"
```

---

## 🧠 Architecture IA

```
Frame/Image
    ↓
FaceDetector (InsightFace buffalo_l)
    ↓ bbox + landmarks + embedding
LivenessDetector (LBP + EAR + optical flow)
    ↓ is_live + score
FaceEmbedder (ArcFace 512D ONNX)
    ↓ vecteur 512D normalisé L2
Supabase pgvector RPC search_face()
    ↓ identités les plus proches (cosine similarity)
PipelineResult → API Response
```

---

## 📁 Structure projet

```
biometric-system/
├── services/
│   ├── ai-core/
│   │   ├── detector.py      # Détection InsightFace
│   │   ├── embedder.py      # Embeddings ArcFace
│   │   ├── anti_spoof.py    # Liveness detection
│   │   └── pipeline.py      # Orchestrateur principal
│   └── api-gateway/
│       ├── main.py          # FastAPI app
│       ├── config.py        # Settings
│       ├── routers/         # Endpoints
│       ├── models/          # Schémas Pydantic
│       └── database/        # Client Supabase
├── supabase/
│   └── migrations/
│       └── 001_initial_schema.sql
├── infra/docker/
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 🗄️ Tables Supabase

| Table | Description |
|-------|-------------|
| `identities` | Personnes enregistrées |
| `face_embeddings` | Vecteurs 512D (pgvector) |
| `unknown_faces` | Inconnus en attente |
| `recognition_events` | Journal détections |
| `access_logs` | Journal accès |
| `kyc_sessions` | Sessions KYC |
| `cameras` | Caméras enregistrées |

---

## ⚠️ Sécurité

- Utiliser la **service_role key** (jamais l'anon key) côté backend
- Le RLS est activé sur toutes les tables
- Les embeddings biométriques sont stockés chiffrés en production
- Activer HTTPS en production (certificat Let's Encrypt)

---

## 📌 Prochaine étape — Phase 2

- [ ] FAISS index local (cache des embeddings pour <1ms)
- [ ] Clustering des inconnus (DBSCAN)
- [ ] Dashboard React
- [ ] Flutter app
- [ ] KYC + OCR documents
