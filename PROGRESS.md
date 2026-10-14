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

### Giai đoạn 4 — Log tập trung Loki + Promtail
- Không tìm thấy cấu hình Loki/Promtail trước đó; chỉ có Nginx access/error log trên stdout/stderr và ghi chú đây là giai đoạn sau.
- Thêm Loki `grafana/loki:3.7.8` với lưu trữ filesystem và retention 7 ngày trên volume `loki_data`; không publish cổng host.
- Thêm Promtail `grafana/promtail:3.5.8`, chỉ thu container có nhãn Compose project `library-management`, với labels project/service/container; giữ vị trí đọc trên volume `promtail_positions`.
- Provision datasource Loki vào Grafana; `loki` cùng mạng `monitoring_net` để Grafana truy vấn và `logging_net` dùng riêng cho Promtail.
- `docker compose config --quiet` — hợp lệ; image `grafana/loki:3.7.8` và `grafana/promtail:3.5.8` đã tải, cả hai container đang chạy. Loki `/ready` trả 200.
- Restart riêng Grafana để nạp provisioning; API health datasource `Loki` trả `Data source successfully connected`.
- Promtail Docker discovery tìm thấy container của project; trong 10 phút truy vấn có log từ `nginx`, `web` (Flask/Gunicorn) và `db` (PostgreSQL). Marker 404 thử nghiệm xuất hiện ở log Nginx và web; marker `SELECT` read-only xuất hiện trong log PostgreSQL.
- Ba LogQL query chạy thành công qua Grafana datasource proxy: xem log `{project="library-management"}` (100 dòng trả về trong cửa sổ 10 phút), lọc 404 `{project="library-management", service="nginx"} |= "/__loki_probe_404"` (3 dòng), và đếm `sum(count_over_time({project="library-management", service=~"nginx|web|db"}[5m]))` (171 dòng).
- Nginx `/healthz` trả 200, PostgreSQL `database: ok`; 5/5 Prometheus targets vẫn **UP**.
- Khi Promtail đọc lại một số file log cũ lúc khởi động, Loki từ chối 7 entry quá cũ/thứ tự đến muộn trong 5 phút đầu. Không có lỗi gửi của Promtail hay từ chối kiểu này trong phút kiểm tra gần nhất; các log mới và marker trên đã được truy vấn thành công.
- Promtail đã EOL từ 02/03/2026; dùng phiên bản 3.5.8 theo yêu cầu giai đoạn, cần lên kế hoạch thay bằng Grafana Alloy.

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

- Chưa đăng nhập website bằng tài khoản quản trị thật trên database production; các luồng đăng nhập/nghiệp vụ được thử trên database scratch riêng. CLI tạo admin bằng terminal tương tác đã thử, mật khẩu không hiện ra trong terminal output.
- Chưa mở Grafana bằng trình duyệt để đánh giá trực quan các panel; datasource, dashboard và truy vấn metrics/logs đã xác nhận qua API.
- Promtail hết hỗ trợ từ 02/03/2026; giữ bản 3.5.8 theo yêu cầu đề tài. Cần lên kế hoạch chuyển sang Grafana Alloy.

## Giai đoạn 5 — Hardening và kiểm chứng tổng thể (2026-10-14)

### Cấu hình và bảo mật

- Tạo role runtime `library_app` riêng cho Flask. `web` chỉ nhận `PGUSER`/`PGPASSWORD` của role này; `POSTGRES_USER`/`POSTGRES_PASSWORD` không còn được truyền vào container web.
- Thêm `database/setup_app_role.sql`, chạy tự động trên volume DB mới và chạy thủ công được trên DB hiện hữu. Role có `CONNECT`, `USAGE` schema, CRUD trên đúng bốn bảng ứng dụng và quyền dùng identity sequence; không có `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `BYPASSRLS`, membership hoặc quyền DDL.
- Sửa `database/init_monitoring.sql` để tự đọc `PG_EXPORTER_PASSWORD`, dùng được khi init DB mới và provision lại DB hiện có mà không truyền mật khẩu trên command line. `postgres_exporter` giữ `pg_monitor` và không có quyền elevated.
- Web chạy `app:app`, root filesystem read-only, `/tmp` tmpfs, `cap_drop: ALL`, `no-new-privileges`. Hai exporter cũng chạy root filesystem read-only, bỏ capabilities và bật `no-new-privileges`.
- Nginx bỏ toàn bộ capabilities ngoại trừ `NET_BIND_SERVICE`, `CHOWN`, `SETUID`, `SETGID` cần cho cổng 80, thư mục temp và worker không-root; bật `no-new-privileges`. Nginx root filesystem vẫn writable vì image cần tạo/chown thư mục cache lúc khởi động.
- DB, web, cAdvisor và exporters không publish cổng host. pgAdmin, Nginx, Prometheus, Grafana bind loopback. Các dịch vụ dùng các mạng Compose đã tách. cAdvisor vẫn cần `privileged`; Promtail vẫn cần Docker socket và đọc container logs.
- `.env` vẫn bị Git ignore; `.env.example` chỉ có giá trị mẫu. Không đổi mật khẩu bootstrap/pgAdmin/Grafana hiện có; chỉ thêm `APP_DB_USER` và khóa ngẫu nhiên riêng cho role web trong `.env` local.

### Kết quả kiểm tra thật

- `docker compose config --quiet` — đạt; `docker compose up -d --build` cho project hiện tại — đạt, không xóa/recreate named volumes.
- DB hiện tại: provisioning role thành công. Role `library_app` có các cờ elevated đều `false`; role website runtime được xác nhận bằng `SELECT current_user` là `library_app`. Bộ đếm trước/sau provisioning giữ nguyên `6 sách : 4 độc giả : 1 lượt mượn : 1 tài khoản`.
- Website `/healthz` trả `status=ok`, `database=ok`; Nginx `nginx -t` thành công; `/login` và `/static/styles.css` trả 200, ba security headers đúng. pgAdmin login page trả 200.
- Web container có user `app:app`, root filesystem read-only, cap drop ALL, no-new-privileges và không publish port. Nginx worker chạy user `nginx`; exporters không publish port, root filesystem read-only và cap drop ALL.
- Prometheus targets: 5/5 UP (`prometheus`, `cadvisor`, `web`, `nginx-exporter`, `postgres-exporter`). Grafana API truy vấn `up` trả 5 series, `pg_up=1`, và `flask_http_request_total` có 2 series.
- Sau khi tạo một HTTP 404 thử nghiệm qua Nginx, Grafana datasource Loki chạy được: xem log (`limit=200`, trả 200 entries trong lần lấy mẫu), marker `/__loki_probe_404` trả 1 entry, regex status 4xx/5xx trả 1 entry thật, query `sum(count_over_time(...[5m]))` trả dữ liệu. Truy vấn riêng theo nhãn 60 phút cho thấy `db=27`, `web=500` và `nginx=500` entries; hai giá trị cuối chạm limit lấy mẫu 500. Log có cả Nginx, Flask/Gunicorn và PostgreSQL.
- Database mới trong project test khác được init tự động: 5 sách, 3 độc giả; role app/exporter đạt kiểm tra quyền; admin được tạo bằng CLI với mật khẩu nhập ẩn; Grafana provision datasource `Prometheus`, `Loki` và dashboard `Library Monitoring`; API query trả 5 target.
- `tests/verify_flows.py` chạy trên DB scratch: thêm/sửa/tìm sách và độc giả; mượn cuốn còn, từ chối khi hết; hai request song song tranh cuốn cuối chỉ một request tạo lượt mượn; trả sách và từ chối trả lần hai; chặn giảm số lượng dưới số đang mượn; từ chối xóa sách/độc giả có lịch sử và giữ bản ghi; login/logout/protected page/CSRF/password hash. Kiểm tra headers, CSS, login/logout/CSRF qua Nginx cũng đạt.
- Fresh stack cuối cùng chạy `docker compose -p library-hardening-fresh-20261014 up -d --build` thành công trên cổng thử `18281`, `15505`, `19091`, `13001`; DB/web/Nginx healthy, pgAdmin 200, Grafana API healthy, 5/5 target UP. Stack đã dừng bằng `down` không `-v`; cả sáu test volumes được giữ.
- Một project scratch bổ sung (`library-hardening-verify-20261014`) cũng được dừng không `-v`; sáu test volumes của project này được giữ. Sáu production volumes (`postgres_data`, `pgadmin_data`, `prometheus_data`, `grafana_data`, `loki_data`, `promtail_positions`) còn nguyên.

### Giới hạn

- Không dùng tài khoản admin thật hoặc sửa/xóa dữ liệu production; các thao tác nghiệp vụ chỉ chạy trên database scratch.
- API Grafana đã được thử, nhưng chưa mở dashboard bằng trình duyệt và chưa chụp ảnh báo cáo.
- Promtail đã EOL từ 02/03/2026; giữ theo yêu cầu đề tài, cần thay bằng Alloy trước khi dùng lâu dài.
