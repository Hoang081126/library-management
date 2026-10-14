# Tiến độ dự án quản lý thư viện

Trang này ghi lại các giai đoạn đã hoàn thành và kết quả kiểm tra thực tế.

## Đã hoàn thành

### Giai đoạn 1 — Website Flask/Jinja + PostgreSQL (commit `e0faac7`)
- Đăng nhập/đăng xuất, CSRF, quản lý sách, độc giả, mượn/trả, trang tổng quan.
- Schema `users`, `books`, `readers`, `loans` trong `database/init.sql`.
- Healthcheck `/healthz` kiểm tra kết nối PostgreSQL.

### Giai đoạn 2 — Nginx reverse proxy và header bảo mật (commit `cef57c7`)
- Thêm service `nginx` (`nginx:stable-alpine`), chỉ Nginx publish `127.0.0.1:8081`.
- `web` không publish cổng host; Nginx và web dùng mạng riêng `proxy_net`.
- Header bảo mật `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- Forwarded headers đầy đủ; Flask dùng `ProxyFix(..., x_for=1, x_proto=1, x_host=1, x_port=1)`.
- Access/error log Nginx ghi stdout/stderr, sẵn sàng cho Loki + Promtail.

### Giai đoạn 3 — Giám sát Prometheus + Grafana (commit hiện tại)
- Thêm `prometheus` (`prom/prometheus:v3.15.0`, `127.0.0.1:9090`), `grafana` (`grafana/grafana:13.2.3`, `127.0.0.1:3000`), `cadvisor` (`ghcr.io/google/cadvisor:0.55.1`), `postgres-exporter` (`quay.io/prometheuscommunity/postgres-exporter:v0.20.1`), `nginx-exporter` (`nginx/nginx-prometheus-exporter:1.4.1`) trên mạng `monitoring_net`.
- Web thêm metrics Flask bằng `prometheus-flask-exporter==0.23.2` (`/metrics`), bỏ theo dõi `/healthz`.
- Gunicorn chạy 1 worker (8 threads) để registry metrics không bị chia theo process.
- Nginx: chặn `GET /metrics` từ ngoài (404), thêm `stub_status` nội bộ trên cổng 8080 cho nginx-exporter.
- PostgreSQL: bật `pg_stat_statements`, tạo role `postgres_exporter` với `pg_monitor` (`database/init_monitoring.sql`).
- Grafana provision datasource `Prometheus` và dashboard **Library Monitoring** (3 nhóm Container/Web/Database).

## Kết quả kiểm tra (2026-10-14)

- `docker compose config --quiet` — hợp lệ.
- `docker compose up -d --build` — 9 service đều chạy (`db`, `pgadmin`, `web`, `nginx`, `prometheus`, `grafana`, `cadvisor`, `postgres-exporter`, `nginx-exporter`).
- Prometheus targets: 5/5 đều **UP** (`prometheus`, `cadvisor`, `web`, `nginx-exporter`, `postgres-exporter`).
- Metrics có dữ liệu thật:
  - Container: CPU 11 series, RAM 12 series (theo `container_id`).
  - Web: `flask_http_request_total` theo status 200/302/400; `flask_http_request_duration_seconds` (p95); `nginx_http_requests_total`.
  - DB: `pg_up=1`, `pg_stat_database_numbackends`, `pg_stat_database_xact_commit/rollback`, `pg_stat_database_blks_hit/read` (cache hit), `pg_database_size_bytes`, `pg_stat_activity_count` theo state, `pg_stat_database_tup_*`.
- Kiểm tra counter tăng: `sum(flask_http_request_total)` từ 31 → 43 sau khi tạo thêm 12 request `GET /login`.
- Grafana: health OK (13.2.3); datasource `Prometheus` (uid `prometheus`, default) hoạt động qua proxy (query `up` trả 5 target = 1); dashboard `Library Monitoring` (uid `library-monitoring`) được provision.
- Website qua Nginx vẫn hoạt động: `GET /healthz` 200, `GET /` 302, `GET /login` 200; `GET /metrics` qua Nginx trả 404.

## Giới hạn thực tế (Docker Desktop/WSL2)

- cAdvisor không lấy được **tên container** (docker factory không đăng ký được do thiếu containerd socket), nên metrics chỉ có nhãn `id`; đã rút gọn thành `container_id` (12 ký tự đầu) qua `metric_relabel_configs`.
- cAdvisor không có **network theo từng container** (chỉ có lưu lượng theo interface Docker ở `id="/"`); dashboard hiển thị lưu lượng theo interface thay vì theo container.
- `postgres-exporter` v0.20.1 chỉ export `pg_settings_pg_stat_statements_*` (cấu hình), không export query-level `pg_stat_statements_calls_total`; dashboard dùng metrics tuple/giao dịch thay thế.

## Chưa kiểm tra / ghi chú

- Chưa đăng nhập bằng tài khoản quản trị thật của website (không dùng mật khẩu có sẵn trong phiên này).
- Chưa đăng nhập Grafana bằng trình duyệt để xem dashboard trực quan (đã xác nhận qua API: datasource hoạt động, dashboard được provision, các query trả về dữ liệu).
- Loki/Promtail và log tập trung — làm ở giai đoạn sau.
