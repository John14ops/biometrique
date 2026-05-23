"""
Schémas Pydantic — validation requêtes/réponses API
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Any
from datetime import datetime
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class IdentityRole(str, Enum):
    user      = "user"
    admin     = "admin"
    vip       = "vip"
    blocked   = "blocked"


class IdentityStatus(str, Enum):
    active   = "active"
    inactive = "inactive"
    blocked  = "blocked"


class EventType(str, Enum):
    recognized     = "recognized"
    unknown        = "unknown"
    rejected       = "rejected"
    spoof_detected = "spoof_detected"


class AccessDecision(str, Enum):
    granted = "granted"
    denied  = "denied"
    alert   = "alert"


# ============================================================
# IDENTITÉS
# ============================================================

class IdentityCreate(BaseModel):
    full_name:  str = Field(..., min_length=2, max_length=100)
    email:      Optional[EmailStr] = None
    phone:      Optional[str] = None
    role:       IdentityRole = IdentityRole.user
    department: Optional[str] = None
    metadata:   Optional[dict] = {}


class IdentityUpdate(BaseModel):
    full_name:  Optional[str] = None
    email:      Optional[EmailStr] = None
    phone:      Optional[str] = None
    role:       Optional[IdentityRole] = None
    status:     Optional[IdentityStatus] = None
    department: Optional[str] = None
    metadata:   Optional[dict] = None


class IdentityResponse(BaseModel):
    id:          str
    full_name:   str
    email:       Optional[str]
    role:        str
    status:      str
    department:  Optional[str]
    created_at:  datetime

    class Config:
        from_attributes = True


# ============================================================
# RECONNAISSANCE
# ============================================================

class RecognizeRequest(BaseModel):
    """Requête de reconnaissance — image en base64"""
    image_base64:   str = Field(..., description="Image encodée base64 (JPEG/PNG)")
    camera_id:      Optional[str] = "default"
    location:       Optional[str] = None
    check_liveness: bool = True


class RecognizeImageFile(BaseModel):
    """Requête via upload multipart"""
    camera_id:      Optional[str] = "default"
    location:       Optional[str] = None
    check_liveness: bool = True


class MatchInfo(BaseModel):
    identity_id: str
    full_name:   str
    role:        str
    similarity:  float


class RecognizeResponse(BaseModel):
    success:         bool
    event_type:      str
    face_count:      int
    matches:         list[MatchInfo] = []
    unknown_id:      Optional[str] = None
    is_live:         bool = True
    liveness_score:  float = 1.0
    quality_score:   float = 0.0
    processing_ms:   float = 0.0
    event_id:        Optional[str] = None
    error:           Optional[str] = None


# ============================================================
# ENRÔLEMENT
# ============================================================

class EnrollRequest(BaseModel):
    identity_id:  str
    image_base64: str


class EnrollResponse(BaseModel):
    success:       bool
    embedding_id:  Optional[str] = None
    quality_score: float = 0.0
    face_count:    int = 0
    error:         Optional[str] = None


# ============================================================
# INCONNUS
# ============================================================

class ResolveUnknownRequest(BaseModel):
    unknown_id:  str
    identity_id: Optional[str] = None    # Si None → créer nouvelle identité
    new_identity: Optional[IdentityCreate] = None


class UnknownFaceResponse(BaseModel):
    id:           str
    temp_id:      str
    appearances:  int
    first_seen_at: datetime
    last_seen_at:  datetime
    location:     Optional[str]
    cluster_id:   Optional[str]


# ============================================================
# KYC
# ============================================================

class KYCCreateRequest(BaseModel):
    identity_id: Optional[str] = None
    doc_type:    str = Field(..., description="passport|id_card|driver_license")


class KYCSessionResponse(BaseModel):
    id:               str
    session_token:    str
    status:           str
    face_match_score: Optional[float]
    liveness_passed:  bool
    fraud_flags:      list
    created_at:       datetime


# ============================================================
# EVENTS & LOGS
# ============================================================

class RecognitionEventResponse(BaseModel):
    id:             str
    event_type:     str
    confidence:     Optional[float]
    liveness_score: Optional[float]
    camera_id:      Optional[str]
    location:       Optional[str]
    created_at:     datetime
    identity:       Optional[dict] = None


class AccessLogResponse(BaseModel):
    id:           str
    access_point: str
    zone:         Optional[str]
    decision:     str
    reason:       Optional[str]
    created_at:   datetime


# ============================================================
# RÉPONSES GÉNÉRIQUES
# ============================================================

class SuccessResponse(BaseModel):
    success: bool = True
    message: str
    data:    Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error:   str
    detail:  Optional[str] = None


class PaginatedResponse(BaseModel):
    items:  list
    total:  int
    limit:  int
    offset: int
