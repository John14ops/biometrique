-- ============================================================
-- BIOMETRIC SYSTEM — Supabase Schema
-- Activer pgvector pour la recherche vectorielle
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- TABLE: identities
-- Stocke les personnes connues du système
-- ============================================================
CREATE TABLE identities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name       TEXT NOT NULL,
    email           TEXT UNIQUE,
    phone           TEXT,
    role            TEXT NOT NULL DEFAULT 'user',          -- user | admin | vip | blocked
    status          TEXT NOT NULL DEFAULT 'active',        -- active | inactive | blocked
    department      TEXT,
    metadata        JSONB DEFAULT '{}',
    avatar_url      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: face_embeddings
-- Vecteurs faciaux 512D (ArcFace) par identité
-- ============================================================
CREATE TABLE face_embeddings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identity_id     UUID NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    embedding       VECTOR(512) NOT NULL,                  -- ArcFace 512D
    quality_score   FLOAT DEFAULT 0.0,                     -- 0.0 à 1.0
    capture_source  TEXT DEFAULT 'webcam',                 -- webcam | mobile | upload | kyc
    image_hash      TEXT,                                  -- SHA256 de l'image source
    is_primary      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index HNSW pour recherche ANN ultra-rapide
CREATE INDEX idx_embeddings_hnsw
ON face_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_embeddings_identity ON face_embeddings(identity_id);

-- ============================================================
-- TABLE: unknown_faces
-- Visages inconnus détectés en attente de validation admin
-- ============================================================
CREATE TABLE unknown_faces (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    temp_id         TEXT UNIQUE NOT NULL,                  -- ex: Unknown_102
    embedding       VECTOR(512) NOT NULL,
    image_url       TEXT,
    cluster_id      TEXT,                                  -- regroupement par similarité
    appearances     INT DEFAULT 1,
    first_seen_at   TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ DEFAULT NOW(),
    resolved        BOOLEAN DEFAULT FALSE,
    resolved_as     UUID REFERENCES identities(id),
    location        TEXT,
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_unknown_embedding
ON unknown_faces USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- ============================================================
-- TABLE: recognition_events
-- Journal de tous les événements de reconnaissance
-- ============================================================
CREATE TABLE recognition_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identity_id     UUID REFERENCES identities(id),
    unknown_face_id UUID REFERENCES unknown_faces(id),
    event_type      TEXT NOT NULL,                         -- recognized | unknown | rejected | spoof_detected
    confidence      FLOAT,                                 -- score similarité 0.0 à 1.0
    liveness_score  FLOAT,                                 -- score anti-spoof 0.0 à 1.0
    camera_id       TEXT,
    location        TEXT,
    image_url       TEXT,
    bbox            JSONB,                                 -- {x, y, w, h}
    landmarks       JSONB,                                 -- 68 points faciaux
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_identity ON recognition_events(identity_id);
CREATE INDEX idx_events_created  ON recognition_events(created_at DESC);
CREATE INDEX idx_events_type     ON recognition_events(event_type);

-- ============================================================
-- TABLE: access_logs
-- Journaux contrôle d'accès
-- ============================================================
CREATE TABLE access_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identity_id     UUID REFERENCES identities(id),
    event_id        UUID REFERENCES recognition_events(id),
    access_point    TEXT NOT NULL,                         -- porte_A | parking | serveur_salle
    zone            TEXT,
    decision        TEXT NOT NULL,                         -- granted | denied | alert
    reason          TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_access_identity ON access_logs(identity_id);
CREATE INDEX idx_access_created  ON access_logs(created_at DESC);

-- ============================================================
-- TABLE: kyc_sessions
-- Sessions KYC : comparaison selfie ↔ document
-- ============================================================
CREATE TABLE kyc_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identity_id     UUID REFERENCES identities(id),
    session_token   TEXT UNIQUE DEFAULT gen_random_uuid()::TEXT,
    status          TEXT DEFAULT 'pending',                -- pending | processing | approved | rejected
    selfie_url      TEXT,
    doc_type        TEXT,                                  -- passport | id_card | driver_license
    doc_image_url   TEXT,
    doc_data        JSONB,                                 -- données OCR extraites
    face_match_score FLOAT,
    liveness_passed BOOLEAN DEFAULT FALSE,
    fraud_flags     JSONB DEFAULT '[]',
    reviewed_by     UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: cameras
-- Caméras enregistrées dans le système
-- ============================================================
CREATE TABLE cameras (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    stream_url      TEXT,
    location        TEXT,
    zone            TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    config          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TRIGGERS: updated_at automatique
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_identities_updated
    BEFORE UPDATE ON identities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_kyc_updated
    BEFORE UPDATE ON kyc_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- FONCTIONS SUPABASE: recherche vectorielle
-- ============================================================

-- Recherche 1:N — trouver les N visages les plus proches
CREATE OR REPLACE FUNCTION search_face(
    query_embedding VECTOR(512),
    match_threshold FLOAT DEFAULT 0.6,
    match_count     INT   DEFAULT 5
)
RETURNS TABLE (
    identity_id   UUID,
    full_name     TEXT,
    role          TEXT,
    status        TEXT,
    similarity    FLOAT,
    embedding_id  UUID
)
LANGUAGE sql STABLE AS $$
    SELECT
        i.id,
        i.full_name,
        i.role,
        i.status,
        1 - (fe.embedding <=> query_embedding) AS similarity,
        fe.id
    FROM face_embeddings fe
    JOIN identities i ON fe.identity_id = i.id
    WHERE i.status = 'active'
      AND 1 - (fe.embedding <=> query_embedding) > match_threshold
    ORDER BY fe.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Recherche parmi inconnus
CREATE OR REPLACE FUNCTION search_unknown_faces(
    query_embedding VECTOR(512),
    match_threshold FLOAT DEFAULT 0.7,
    match_count     INT   DEFAULT 3
)
RETURNS TABLE (
    unknown_id  UUID,
    temp_id     TEXT,
    similarity  FLOAT,
    appearances INT
)
LANGUAGE sql STABLE AS $$
    SELECT
        id,
        temp_id,
        1 - (embedding <=> query_embedding) AS similarity,
        appearances
    FROM unknown_faces
    WHERE resolved = FALSE
      AND 1 - (embedding <=> query_embedding) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE identities       ENABLE ROW LEVEL SECURITY;
ALTER TABLE face_embeddings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE recognition_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE access_logs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE unknown_faces    ENABLE ROW LEVEL SECURITY;
ALTER TABLE kyc_sessions     ENABLE ROW LEVEL SECURITY;

-- Service role a accès total (backend)
CREATE POLICY "service_role_all" ON identities
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "service_role_all" ON face_embeddings
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "service_role_all" ON recognition_events
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "service_role_all" ON access_logs
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "service_role_all" ON unknown_faces
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "service_role_all" ON kyc_sessions
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

-- ============================================================
-- DONNÉES INITIALES
-- ============================================================
INSERT INTO cameras (name, location, zone, is_active)
VALUES
    ('Entrée principale', 'Lobby', 'public', TRUE),
    ('Salle serveur', 'Bâtiment B', 'secured', TRUE),
    ('Parking', 'Sous-sol', 'restricted', TRUE);
