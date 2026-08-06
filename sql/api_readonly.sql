-- Rol de solo lectura para la API que consume SIGTAR.
--
-- El bot conserva su usuario con permisos de escritura. La API se conecta con
-- este rol, de modo que un fallo en el servicio expuesto no pueda alterar ni
-- borrar reportes: como mucho podría leer lo que ya publica por HTTP.
--
-- Este archivo NO se ejecuta en el arranque (a diferencia de schema.sql). Se
-- aplica una sola vez contra la base ya creada, sustituyendo la contraseña:
--
--   docker compose exec -T postgres \
--     psql -U galapagos -d galapagos_previene \
--     -v api_password="'una_clave_larga_y_aleatoria'" < sql/api_readonly.sql
--
-- La contraseña debe coincidir con la del DATABASE_URL del servicio `api`.

\set ON_ERROR_STOP on

-- CREATE ROLE no admite IF NOT EXISTS, así que se comprueba antes para que el
-- script pueda repetirse sin fallar (por ejemplo al rotar la contraseña).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'galapagos_api') THEN
        CREATE ROLE galapagos_api LOGIN;
    END IF;
END
$$;

ALTER ROLE galapagos_api WITH PASSWORD :api_password;

-- Sin CREATE sobre el esquema el rol tampoco puede crear tablas propias.
GRANT CONNECT ON DATABASE galapagos_previene TO galapagos_api;
GRANT USAGE ON SCHEMA public TO galapagos_api;

GRANT SELECT ON
    reports,
    report_media,
    event_types,
    telegram_users
TO galapagos_api;

-- Las tablas que se creen después heredan el mismo permiso de lectura, para
-- que ampliar el esquema no obligue a recordar este archivo.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO galapagos_api;

-- Verificación: debe devolver cuatro filas, todas con privilege_type SELECT.
SELECT table_name, privilege_type
FROM information_schema.table_privileges
WHERE grantee = 'galapagos_api'
ORDER BY table_name;
