# Hệ thống quản lý thư viện

Website nội bộ dùng Flask, Jinja, CSS và PostgreSQL 17. Ứng dụng sử dụng các bảng `users`, `books`, `readers`, `loans` được khai báo trong `database/init.sql`; không tự tạo lại hoặc đổi tên bảng/cột.

Kiến trúc hiện tại có Nginx làm reverse proxy duy nhất:

- **Nginx** publish `127.0.0.1:8081` ra máy hiện tại; chỉ nó nằm trên mạng `proxy_net` với `web`.
- **web** (Flask/Gunicorn) chạy nội bộ trên mạng `proxy_net` + `database_net`, **không** publish cổng host.
- **pgAdmin** ở `http://localhost:5055`; **db** (PostgreSQL 17) chỉ nội bộ trên `database_net`.
- Website ở `http://localhost:8081` trên máy hiện tại (cổng 8080 đã có dịch vụ Apache).
- Giám sát: **Prometheus** `http://localhost:9090`, **Grafana** `http://localhost:3000` (xem mục Giám sát bên dưới).

## Chạy website

1. Đảm bảo Docker Desktop đang chạy và các biến PostgreSQL/pgAdmin hiện có trong `.env` vẫn đúng. Không ghi đè `.env` hiện tại bằng file mẫu.
2. Khóa phiên Flask được giữ trong `.env`. Nếu chưa có, thêm khóa ngẫu nhiên riêng vào đó, ví dụ tạo bằng PowerShell:

   ```powershell
   $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
   [byte[]]$bytes = New-Object byte[] 32
   $rng.GetBytes($bytes)
   $key = ([BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
   Add-Content .env "FLASK_SECRET_KEY=$key"
   $rng.Dispose()
   Remove-Variable key, bytes, rng
   ```

   Không gửi hoặc commit `.env`. `.env.example` chỉ có giá trị minh họa cho cài đặt mới.

3. Từ thư mục dự án, build và khởi động dịch vụ:

   ```powershell
   docker compose up -d --build
   docker compose ps
   ```

   `web` đợi `db` khỏe trước khi khởi động; `nginx` đợi `web` khỏe. Healthcheck website gọi `/healthz`, endpoint này thử kết nối PostgreSQL. Các volume `postgres_data` và `pgadmin_data` được giữ nguyên.

4. Mở [http://localhost:8081](http://localhost:8081). Toàn bộ traffic đi qua Nginx; chỉ Nginx bind vào loopback `127.0.0.1` để dùng tại máy hiện tại.

## Reverse proxy và header bảo mật

`nginx/default.conf` proxy tới `web:8080` và thêm các header:

- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
- Forwarded headers `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`.

Flask bọc `ProxyFix` với `x_for=1, x_proto=1, x_host=1, x_port=1`, chỉ tin đúng một lớp proxy. Access/error log của Nginx ghi ra stdout/stderr để sẵn sàng cho Loki + Promtail ở giai đoạn sau.

Kiểm tra cấu hình Nginx:

```powershell
docker compose exec nginx nginx -t
```

## Tạo tài khoản quản trị

Chạy lệnh tương tác sau khi dịch vụ `web` đã chạy; mật khẩu được nhập ẩn và không nằm trong command history:

```powershell
docker compose exec web flask --app app create-admin
```

Tên đăng nhập chỉ gồm chữ/số/dấu `.`, `_`, `-` và dài 3–50 ký tự. Mật khẩu tối thiểu 12 ký tự, được băm trước khi lưu vào `users.password_hash`. Lệnh sẽ báo nếu tên đăng nhập đã tồn tại.

## Kiểm tra chức năng

- Đăng nhập, rồi xem tổng số đầu sách, tổng số cuốn, độc giả, lượt đang mượn và lượt quá hạn trên trang tổng quan.
- Thêm/sửa/tìm/xóa một sách và độc giả. Thử mã trùng, năm hoặc số lượng không hợp lệ; thông báo hiển thị bằng tiếng Việt.
- Mượn một cuốn, thử mượn hết số lượng có sẵn, sau đó trả lượt mượn. Lượt đã trả không thể trả lần thứ hai; lịch sử vẫn được giữ.
- Thử xóa sách hoặc độc giả đã xuất hiện trong lịch sử mượn, và thử giảm số lượng sách xuống dưới số cuốn đang mượn.
- Xem trạng thái dịch vụ và healthcheck bằng `docker compose ps`; kiểm tra nhật ký bằng `docker compose logs web` hoặc `docker compose logs nginx`.
- Có thể kiểm tra endpoint DB qua proxy bằng `Invoke-RestMethod http://localhost:8081/healthz`; khi khỏe, kết quả có `status: ok` và `database: ok`.

Các thao tác thêm, sửa, xóa, mượn, trả và đăng xuất dùng POST có CSRF token. Đăng nhập yêu cầu mật khẩu băm, không có tài khoản hoặc mật khẩu mặc định trong source. Các yêu cầu mượn cùng sách được tuần tự hóa bằng khóa hàng PostgreSQL trong transaction, sau đó mới đếm lượt chưa trả và tạo lượt mới.

## Giám sát (Prometheus + Grafana)

Các dịch vụ giám sát chạy cùng Compose và chỉ bind `127.0.0.1`:

- **Prometheus** — `http://localhost:9090` (xem targets, truy vấn).
- **Grafana** — `http://localhost:3000`, đăng nhập `admin` + `GRAFANA_ADMIN_PASSWORD` trong `.env`.
- **cAdvisor** — metrics container (CPU/RAM/network), không publish cổng host.
- **postgres-exporter** — metrics PostgreSQL (kết nối, giao dịch, cache, kích thước, tuples…).
- **nginx-exporter** — metrics Nginx (kết nối, request) qua `stub_status` nội bộ.

Grafana provision sẵn datasource `Prometheus` và dashboard **Library Monitoring** gồm ba nhóm Container / Web / Database. Endpoint `/metrics` của Flask chỉ dùng nội bộ cho Prometheus; Nginx trả `404` khi gọi `GET /metrics` từ ngoài.

Thiết lập tài khoản giám sát cho PostgreSQL (chạy một lần; dùng được cho cả DB đã tồn tại lẫn máy mới, không cần xóa volume):

```bash
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v pg_exporter_password="$PG_EXPORTER_PASSWORD" -v ON_ERROR_STOP=1 \
  < database/init_monitoring.sql
```

`database/init_monitoring.sql` tạo role `postgres_exporter` với `pg_monitor` (quyền đọc tối thiểu các view thống kê). `pg_stat_statements` được bật qua `command` của service `db` và `CREATE EXTENSION` trong `database/init.sql`.

Kiểm tra nhanh:

```powershell
# Các target Prometheus đều UP
Invoke-RestMethod http://localhost:9090/api/v1/targets

# Số request của web
Invoke-RestMethod "http://localhost:9090/api/v1/query?query=sum(flask_http_request_total)"
```

Ghi chú Docker Desktop/WSL2: cAdvisor không lấy được tên container (chỉ có `id`, đã rút gọn thành nhãn `container_id`) và không có metrics network theo từng container (chỉ có lưu lượng theo interface Docker). Chi tiết xem `PROGRESS.md`.

## Lưu ý vận hành

- `database/init.sql` của PostgreSQL chỉ chạy khi khởi tạo data directory mới. Thêm web/nginx không xóa volume hay chạy lại script lên database đã có.
- Không dùng `docker compose down -v` nếu muốn giữ dữ liệu hiện có. `docker compose down` không có `-v` vẫn giữ volume.
- Đã có Nginx reverse proxy và giám sát Prometheus/Grafana. Loki/Promtail và log tập trung làm ở giai đoạn sau.
