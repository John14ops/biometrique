"""
BIOMETRIC SYSTEM — Point d'entrée FastAPI
Démarre avec: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../ai-core"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger
import time

from config import get_settings
from routers.recognize import router as recognize_router
from routers.identity import router as identity_router, unknowns_router
from routers.websocket import router as ws_router

settings = get_settings()


# ============================================================
# LIFESPAN — initialisation au démarrage
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Démarrage Biometric System API...")

    # Initialiser le pipeline IA
    try:
        from pipeline import get_pipeline
        pipeline = get_pipeline()
        logger.success("Pipeline IA initialisé")
    except Exception as e:
        logger.warning(f"Pipeline init: {e}")

    # Vérifier connexion Supabase
    try:
        from database.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("cameras").select("id").limit(1).execute()
        logger.success("Supabase connecté ✓")
    except Exception as e:
        logger.warning(f"Supabase connexion: {e}")

    logger.success(f"API prête sur http://{settings.app_host}:{settings.app_port}")
    yield
    logger.info("Arrêt de l'API...")


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Biometric Recognition System",
    description=(
        "API professionnelle de reconnaissance faciale biométrique.\n\n"
        "**Fonctionnalités:**\n"
        "- Détection et reconnaissance faciale temps réel\n"
        "- Anti-spoofing (liveness detection)\n"
        "- KYC biométrique\n"
        "- Contrôle d'accès intelligent\n"
        "- WebSocket pour flux caméra continu\n"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ============================================================
# MIDDLEWARE
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Ajoute X-Process-Time à chaque réponse"""
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.perf_counter() - t0) * 1000:.1f}ms"
    return response


# ============================================================
# ROUTES
# ============================================================

app.include_router(recognize_router)
app.include_router(identity_router)
app.include_router(unknowns_router)
app.include_router(ws_router)


# ============================================================
# ENDPOINTS UTILITAIRES
# ============================================================

@app.get("/", tags=["Santé"])
async def root():
    return {
        "service": "Biometric Recognition System",
        "version": "1.0.0",
        "status":  "running",
        "docs":    "/docs",
    }


@app.get("/health", tags=["Santé"])
async def health_check():
    """Vérification santé pour Docker/Kubernetes"""
    checks = {}

    # Supabase
    try:
        from database.supabase_client import get_supabase
        get_supabase().table("cameras").select("id").limit(1).execute()
        checks["supabase"] = "ok"
    except Exception as e:
        checks["supabase"] = f"error: {e}"

    # Pipeline IA
    try:
        from pipeline import get_pipeline
        get_pipeline()
        checks["ai_pipeline"] = "ok"
    except Exception as e:
        checks["ai_pipeline"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "healthy" if all_ok else "degraded",
            "checks": checks,
            "gpu":    settings.gpu_enabled,
            "model":  settings.face_detection_model,
        }
    )


@app.get("/api/v1/stats", tags=["Analytics"])
async def get_stats():
    """Statistiques générales du système"""
    from database.supabase_client import get_supabase
    sb = get_supabase()

    identities  = sb.table("identities").select("id", count="exact").execute()
    embeddings  = sb.table("face_embeddings").select("id", count="exact").execute()
    events      = sb.table("recognition_events").select("id", count="exact").execute()
    unknowns    = sb.table("unknown_faces").select("id", count="exact").eq("resolved", False).execute()

    return {
        "identities":     identities.count or 0,
        "embeddings":     embeddings.count or 0,
        "total_events":   events.count or 0,
        "pending_unknowns": unknowns.count or 0,
    }


# ============================================================
# GESTION D'ERREURS GLOBALE
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erreur non gérée: {exc} | {request.url}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Erreur interne", "detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        workers=1,    # 1 worker en dev (GPU partagé)
    )
