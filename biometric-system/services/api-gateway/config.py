"""
Configuration centralisée — chargée depuis .env
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True
    secret_key: str = "change_me"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str = ""

    # IA
    face_detection_model: str = "buffalo_l"
    embedding_model: str = "arcface_r100"
    anti_spoof_model: str = "minivision"
    model_dir: str = "./models"
    similarity_threshold: float = 0.6
    liveness_threshold: float = 0.5

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl: int = 300

    # Storage
    storage_bucket: str = "biometric-media"
    max_image_size_mb: int = 5

    # Performance
    gpu_enabled: bool = False
    batch_size: int = 8
    max_faces_per_frame: int = 10
    fps_target: int = 30

    # Sécurité
    jwt_expire_minutes: int = 60
    api_key_header: str = "X-API-Key"
    rate_limit_per_minute: int = 100

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
