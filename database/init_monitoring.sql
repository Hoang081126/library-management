-- Tạo tài khoản giám sát cho postgres_exporter với quyền tối thiểu.
--
-- Chạy thủ công một lần cho database đã tồn tại (không cần xóa volume):
--   docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--     -v pg_exporter_password="$PG_EXPORTER_PASSWORD" -v ON_ERROR_STOP=1 \
--     < database/init_monitoring.sql
--
-- `pg_monitor` là role định sẵn của PostgreSQL, chỉ cấp quyền đọc các view
-- pg_stat_* / pg_settings, đủ cho exporter mà không cấp quyền trên dữ liệu ứng dụng.
-- Dùng \gexec để tạo role một cách idempotent mà không đặt mật khẩu vào source.

SELECT format(
    'CREATE ROLE postgres_exporter WITH LOGIN PASSWORD %L CONNECTION LIMIT 3',
    :'pg_exporter_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter')\gexec

SELECT format(
    'ALTER ROLE postgres_exporter WITH LOGIN PASSWORD %L CONNECTION LIMIT 3',
    :'pg_exporter_password'
)
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter')\gexec

GRANT CONNECT ON DATABASE :"DBNAME" TO postgres_exporter;
GRANT pg_monitor TO postgres_exporter;
