-- Consultas administrativas de ejemplo para Galapagos Previene.
-- Son consultas de solo lectura. Ejecutelas con un usuario que tenga unicamente
-- permiso SELECT cuando no sea necesario modificar datos.

-- 1. Reportes enviados recientemente, con usuario, tipo de evento y cantidad
-- de evidencias. COALESCE permite mostrar 0 si no hubiera filas asociadas.
SELECT
    r.id,
    LEFT(r.id::text, 8) AS short_code,
    r.submitted_at,
    r.report_kind,
    et.code AS event_code,
    et.name AS event_name,
    tu.telegram_user_id,
    tu.username,
    r.latitude,
    r.longitude,
    r.description,
    COUNT(rm.id) AS media_count
FROM reports AS r
JOIN telegram_users AS tu ON tu.id = r.user_id
LEFT JOIN event_types AS et ON et.id = r.event_type_id
LEFT JOIN report_media AS rm ON rm.report_id = r.id
WHERE r.status = 'SUBMITTED'
GROUP BY r.id, et.id, tu.id
ORDER BY r.submitted_at DESC NULLS LAST
LIMIT 100;

-- 2. Buscar un reporte por el codigo corto mostrado al usuario. Sustituya
-- 'a1b2c3d4' por los ocho caracteres recibidos. Si se amplía el código corto,
-- ajuste también el valor de LEFT.
SELECT
    r.*,
    tu.telegram_user_id,
    tu.username,
    et.code AS event_code,
    et.name AS event_name
FROM reports AS r
JOIN telegram_users AS tu ON tu.id = r.user_id
LEFT JOIN event_types AS et ON et.id = r.event_type_id
WHERE LEFT(r.id::text, 8) = LOWER('a1b2c3d4');

-- 3. Metadatos de las evidencias de un reporte. PREPARE permite usar $1 como
-- lo haría asyncpg y mantiene ejecutable este archivo completo. Sustituya el
-- UUID del EXECUTE por el reporte que desea revisar.
PREPARE report_media_by_id (uuid) AS
SELECT
    rm.id,
    rm.media_type,
    rm.telegram_message_type,
    rm.telegram_file_id,
    rm.telegram_file_unique_id,
    rm.telegram_message_id,
    rm.telegram_media_group_id,
    rm.mime_type,
    rm.original_file_name,
    rm.file_size,
    rm.width,
    rm.height,
    rm.duration_seconds,
    rm.caption,
    rm.created_at
FROM report_media AS rm
WHERE rm.report_id = $1::uuid
ORDER BY rm.created_at, rm.telegram_message_id;

EXECUTE report_media_by_id('00000000-0000-0000-0000-000000000000');
DEALLOCATE report_media_by_id;

-- 4. Cantidad de reportes enviados por día y clase.
SELECT
    DATE_TRUNC('day', r.submitted_at) AS day,
    r.report_kind,
    COALESCE(et.name, 'No aplica') AS event_type,
    COUNT(*) AS reports
FROM reports AS r
LEFT JOIN event_types AS et ON et.id = r.event_type_id
WHERE r.status = 'SUBMITTED'
  AND r.submitted_at >= NOW() - INTERVAL '30 days'
GROUP BY day, r.report_kind, et.name
ORDER BY day DESC, r.report_kind, event_type;

-- 5. Borradores activos. El índice único parcial garantiza como máximo uno
-- por usuario, pero esta consulta ayuda a detectar flujos abandonados.
SELECT
    r.id,
    tu.telegram_user_id,
    tu.username,
    r.report_kind,
    r.workflow_step,
    r.created_at,
    r.updated_at,
    NOW() - r.updated_at AS inactive_for
FROM reports AS r
JOIN telegram_users AS tu ON tu.id = r.user_id
WHERE r.status = 'DRAFT'
ORDER BY r.updated_at;

-- 6. Álbumes recibidos. Telegram entrega cada elemento en una actualización;
-- por eso cada grupo puede contener varias filas.
SELECT
    rm.report_id,
    rm.telegram_media_group_id,
    COUNT(*) AS items,
    MIN(rm.created_at) AS first_item_at,
    MAX(rm.created_at) AS last_item_at
FROM report_media AS rm
WHERE rm.telegram_media_group_id IS NOT NULL
GROUP BY rm.report_id, rm.telegram_media_group_id
ORDER BY last_item_at DESC;

-- 7. Duplicados por file_unique_id entre reportes. Este identificador sirve
-- para reconocer un archivo; no sirve para descargarlo ni reenviarlo.
SELECT
    rm.telegram_file_unique_id,
    COUNT(*) AS occurrences,
    ARRAY_AGG(DISTINCT rm.report_id) AS report_ids
FROM report_media AS rm
GROUP BY rm.telegram_file_unique_id
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;

-- 8. Verificación rápida de integridad lógica en reportes enviados. El
-- resultado esperado es cero filas.
SELECT r.id, r.report_kind, r.event_type_id, r.latitude, r.longitude, r.description
FROM reports AS r
WHERE r.status = 'SUBMITTED'
  AND (
      r.latitude IS NULL
      OR r.longitude IS NULL
      OR r.description IS NULL
      OR LENGTH(BTRIM(r.description)) < 10
      OR (r.report_kind = 'EVENT' AND r.event_type_id IS NULL)
      OR (r.report_kind = 'INCIDENT' AND r.event_type_id IS NOT NULL)
      OR NOT EXISTS (
          SELECT 1 FROM report_media AS rm WHERE rm.report_id = r.id
      )
  );
