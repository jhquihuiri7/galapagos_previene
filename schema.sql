-- Esquema de PostgreSQL para Galápagos Previene.
--
-- Los UUID se generan en Python con uuid.uuid4(). De este modo el esquema no
-- depende de extensiones opcionales de PostgreSQL y también puede utilizarse
-- en servicios administrados donde no se permita instalar extensiones.

CREATE TABLE IF NOT EXISTS telegram_users (
    id UUID PRIMARY KEY,
    telegram_user_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(64),
    first_name VARCHAR(128),
    last_name VARCHAR(128),
    language_code VARCHAR(16),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event_types (
    id SMALLSERIAL PRIMARY KEY,
    code VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(64) NOT NULL,
    family VARCHAR(32) NOT NULL DEFAULT 'Sin clasificar',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- La columna se añadió después de la primera versión del esquema. El DEFAULT
-- permite que una base ya existente la incorpore sin quedarse sin valor; el
-- upsert de más abajo la rellena con la familia oficial de cada evento.
ALTER TABLE event_types
    ADD COLUMN IF NOT EXISTS family VARCHAR(32) NOT NULL DEFAULT 'Sin clasificar';

-- La carga es idempotente: ejecutar schema.sql otra vez actualiza el nombre, la
-- familia y el estado de los valores oficiales sin crear filas duplicadas.
--
-- Los eventos retirados del catálogo se conservan con is_active = FALSE en
-- lugar de borrarse: la clave foránea es ON DELETE RESTRICT y un reporte
-- histórico debe poder seguir traduciendo su código. El bot solo ofrece los
-- activos, que son los que enumera app.models.EventType.
INSERT INTO event_types (code, name, family, is_active)
VALUES
    ('TSU', 'Tsunami', 'Oceanográfico', TRUE),
    ('LLI', 'Lluvias intensas', 'Hidrometeorológico', TRUE),
    ('INU', 'Inundación', 'Hidrometeorológico', TRUE),
    ('OLJ', 'Oleaje', 'Oceanográfico', TRUE),
    ('SEQ', 'Sequía', 'Hidrometeorológico', TRUE),
    ('AMA', 'Accidente en medios acuáticos', 'Tecnológico', TRUE),
    ('PLG', 'Plaga', 'Biológico', TRUE),
    ('INF', 'Incendio forestal', 'Ambiental', TRUE),
    ('COI', 'Colapso en infraestructura', 'Fallo estructural', TRUE),
    ('VDV', 'Vendaval', 'Hidrometeorológico', TRUE),
    -- Retirados del catálogo que ofrece el bot.
    ('ERV', 'Erupción volcánica', 'Geológico interno', FALSE),
    ('CQM', 'Contaminación química', 'Ambiental', FALSE),
    ('SIS', 'Sismo', 'Geológico interno', FALSE),
    ('DES', 'Deslizamiento', 'Geológico externo', FALSE),
    ('CAD', 'Caídas (Colapso)', 'Geológico externo', FALSE)
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    family = EXCLUDED.family,
    is_active = EXCLUDED.is_active;

CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES telegram_users(id) ON DELETE RESTRICT,
    telegram_chat_id BIGINT NOT NULL,
    report_kind VARCHAR(20) NOT NULL,
    event_type_id SMALLINT REFERENCES event_types(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    workflow_step VARCHAR(40) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location_accuracy DOUBLE PRECISION,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,

    CONSTRAINT reports_kind_check
        CHECK (report_kind IN ('EVENT', 'INCIDENT')),
    CONSTRAINT reports_status_check
        CHECK (status IN ('DRAFT', 'SUBMITTED', 'CANCELLED')),
    CONSTRAINT reports_workflow_step_check
        CHECK (
            workflow_step IN (
                'CHOOSE_EVENT_TYPE',
                'WAITING_MEDIA',
                'WAITING_LOCATION',
                'WAITING_DESCRIPTION',
                'COMPLETED',
                'CANCELLED'
            )
        ),
    CONSTRAINT reports_status_workflow_check
        CHECK (
            (status = 'DRAFT' AND workflow_step IN (
                'CHOOSE_EVENT_TYPE',
                'WAITING_MEDIA',
                'WAITING_LOCATION',
                'WAITING_DESCRIPTION'
            ))
            OR (status = 'SUBMITTED' AND workflow_step = 'COMPLETED')
            OR (status = 'CANCELLED' AND workflow_step = 'CANCELLED')
        ),
    CONSTRAINT reports_incident_without_event_type_check
        CHECK (report_kind = 'EVENT' OR event_type_id IS NULL),
    CONSTRAINT reports_submitted_event_type_check
        CHECK (
            status <> 'SUBMITTED'
            OR report_kind <> 'EVENT'
            OR event_type_id IS NOT NULL
        ),
    CONSTRAINT reports_latitude_check
        CHECK (latitude IS NULL OR latitude BETWEEN -90.0 AND 90.0),
    CONSTRAINT reports_longitude_check
        CHECK (longitude IS NULL OR longitude BETWEEN -180.0 AND 180.0),
    CONSTRAINT reports_location_pair_check
        CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CONSTRAINT reports_location_accuracy_check
        CHECK (
            location_accuracy IS NULL
            OR (latitude IS NOT NULL AND location_accuracy >= 0.0)
        ),
    CONSTRAINT reports_submitted_location_check
        CHECK (
            status <> 'SUBMITTED'
            OR (latitude IS NOT NULL AND longitude IS NOT NULL)
        ),
    CONSTRAINT reports_submitted_description_check
        CHECK (
            status <> 'SUBMITTED'
            OR (
                description IS NOT NULL
                AND CHAR_LENGTH(BTRIM(description)) >= 10
            )
        ),
    CONSTRAINT reports_submitted_at_check
        CHECK ((status = 'SUBMITTED') = (submitted_at IS NOT NULL))
);

-- Esta regla también protege contra carreras entre varios procesos del bot.
-- Los reportes enviados o cancelados no participan en el índice.
CREATE UNIQUE INDEX IF NOT EXISTS reports_one_draft_per_user_uidx
    ON reports (user_id)
    WHERE status = 'DRAFT';

CREATE INDEX IF NOT EXISTS reports_user_id_idx
    ON reports (user_id);

CREATE INDEX IF NOT EXISTS reports_status_idx
    ON reports (status);

CREATE INDEX IF NOT EXISTS reports_created_at_idx
    ON reports (created_at DESC);

-- Sincronización incremental de la API de lectura. El orden coincide con el
-- cursor (updated_at, id) que usan los consumidores externos: sin este índice
-- cada página degenera en un recorrido completo de la tabla.
CREATE INDEX IF NOT EXISTS reports_updated_at_id_idx
    ON reports (updated_at ASC, id ASC);

CREATE TABLE IF NOT EXISTS report_media (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    media_type VARCHAR(10) NOT NULL,
    telegram_message_type VARCHAR(10) NOT NULL,
    telegram_file_id TEXT NOT NULL,
    telegram_file_unique_id VARCHAR(255) NOT NULL,
    telegram_message_id BIGINT NOT NULL,
    telegram_media_group_id VARCHAR(255),
    mime_type VARCHAR(128),
    original_file_name TEXT,
    file_size BIGINT,
    width INTEGER,
    height INTEGER,
    duration_seconds INTEGER,
    caption TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT report_media_type_check
        CHECK (media_type IN ('PHOTO', 'VIDEO')),
    CONSTRAINT report_media_message_type_check
        CHECK (telegram_message_type IN ('PHOTO', 'VIDEO', 'DOCUMENT')),
    CONSTRAINT report_media_message_media_consistency_check
        CHECK (
            telegram_message_type = 'DOCUMENT'
            OR telegram_message_type = media_type
        ),
    CONSTRAINT report_media_file_id_not_blank_check
        CHECK (BTRIM(telegram_file_id) <> ''),
    CONSTRAINT report_media_unique_id_not_blank_check
        CHECK (BTRIM(telegram_file_unique_id) <> ''),
    CONSTRAINT report_media_file_size_check
        CHECK (file_size IS NULL OR file_size >= 0),
    CONSTRAINT report_media_width_check
        CHECK (width IS NULL OR width > 0),
    CONSTRAINT report_media_height_check
        CHECK (height IS NULL OR height > 0),
    CONSTRAINT report_media_duration_check
        CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    CONSTRAINT report_media_report_message_unique
        UNIQUE (report_id, telegram_message_id)
);

CREATE INDEX IF NOT EXISTS report_media_report_id_idx
    ON report_media (report_id);

CREATE INDEX IF NOT EXISTS report_media_telegram_file_id_idx
    ON report_media (telegram_file_id);

CREATE INDEX IF NOT EXISTS report_media_telegram_file_unique_id_idx
    ON report_media (telegram_file_unique_id);

CREATE INDEX IF NOT EXISTS report_media_telegram_media_group_id_idx
    ON report_media (telegram_media_group_id);

-- Migración de la nomenclatura inicial (RAIN, TSUNAMI, FIRE) a los códigos
-- oficiales de tres letras. Va al final del archivo porque necesita que
-- `reports` ya exista. Es idempotente: después de la primera ejecución no
-- quedan filas antiguas y ninguna de las dos sentencias afecta a nada.
UPDATE reports AS report
SET event_type_id = vigente.id
FROM event_types AS antiguo, event_types AS vigente
WHERE report.event_type_id = antiguo.id
  AND vigente.code = CASE antiguo.code
      WHEN 'RAIN' THEN 'LLI'
      WHEN 'TSUNAMI' THEN 'TSU'
      WHEN 'FIRE' THEN 'INF'
  END;

-- Ya sin reportes que los referencien, la clave foránea ON DELETE RESTRICT
-- permite retirarlos del catálogo.
DELETE FROM event_types
WHERE code IN ('RAIN', 'TSUNAMI', 'FIRE');
