# Tiến độ dự án quản lý thư viện

Trang này ghi lại các giai đoạn đã hoàn thành và kết quả kiểm tra thực tế.

## Đã hoàn thành

### Giai đoạn 1 — Website Flask/Jinja + PostgreSQL (commit `e0faac7`)
- Đăng nhập/đăng xuất, CSRF, quản lý sách, độc giả, mượn/trả, trang tổng quan.
- Schema `users`, `books`, `readers`, `loans` trong `database/init.sql`.
- Healthcheck `/healthz` kiểm tra kết nối PostgreSQL.

### Giai đoạn 2 — Nginx reverse proxy và header bảo mật (chưa commit, xem bên dưới)
- Thêm service `nginx` (image `nginx:stable-alpine`), chỉ Nginx publish `127.0.0.1:8081`.
- `web` không publish cổng host; Nginx và web dùng mạng riêng `proxy_net`; `db`/`pgadmin` giữ `database_net`.
- Giữ pgAdmin ở `127.0.0.1:5055`, giữ các volume `postgres_data`, `pgadmin_data`.
- Header bảo mật trong `nginx/default.conf`: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- Forwarded headers đầy đủ; Flask dùng `ProxyFix(x_for=1, x_proto=1, x_host=1, x_port=1)` — chỉ tin một lớp proxy.
- Access/error log Nginx ghi stdout/stderr, sẵn sàng cho Loki + Promtail ở giai đoạn sau.

## Kết quả kiểm tra (2026-10-14)

- `docker compose config --quiet` — hợp lệ.
- `docker compose exec nginx nginx -t` — `syntax is ok` / `test is successful`.
- `docker compose ps` — `db` (healthy), `pgadmin` (up, 127.0.0.1:5055), `web` (healthy, chỉ nội bộ 8080), `nginx` (healthy, 127.0.0.1:8081).
- `GET /healthz` qua proxy — `200`, header bảo mật đầy đủ.
- `GET /` qua proxy — `302` → `Location: /login?next=/`.
- `GET /static/styles.css` qua proxy — `200`, `Content-Type: text/css`, header bảo mật đầy đủ.
- POST `/login` không có CSRF token — `400` (từ chối CSRF).
- POST `/login` có CSRF token + sai mật khẩu — `200` với thông báo "Tên đăng nhập hoặc mật khẩu không đúng" (CSRF qua proxy hoạt động, request đến được logic đăng nhập).

## Chưa kiểm tra / ghi chú

- Chưa đăng nhập bằng tài khoản quản trị thật (không dùng mật khẩu có sẵn trong phiên này).
- Giám sát (Prometheus/Grafana) và log tập trung (Loki + Promtail) — làm ở giai đoạn sau.
