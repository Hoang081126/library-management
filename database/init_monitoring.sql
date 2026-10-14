-- Tạo tài khoản giám sát cho postgres_exporter với quyền tối thiểu.
--
-- Máy mới chạy script này trong docker-entrypoint-initdb.d.
-- Với database đã tồn tại, dùng lệnh psql trong README; script đọc mật khẩu
-- từ môi trường container, không truyền bí mật trên command line.
--
-- `pg_monitor` là role định sẵn của PostgreSQL, chỉ cấp quyền đọc các view
-- pg_stat_* / pg_settings, đủ cho exporter mà không cấp quyền trên dữ liệu ứng dụng.
-- Dùng \gexec để tạo role một cách idempotent mà không đặt mật khẩu vào source.

\set ON_ERROR_STOP on
\getenv pg_exporter_password PG_EXPORTER_PASSWORD

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT format(
    'CREATE ROLE postgres_exporter WITH LOGIN PASSWORD %L CONNECTION LIMIT 3',
    :'pg_exporter_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter')\gexec

SELECT format(
    'ALTER ROLE postgres_exporter WITH LOGIN PASSWORD %L CONNECTION LIMIT 3 INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'pg_exporter_password'
)
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter')\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO postgres_exporter', current_database())\gexec
GRANT pg_monitor TO postgres_exporter;
