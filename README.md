# Hệ thống quản lý thư viện

Website nội bộ dùng Flask, Jinja, CSS và PostgreSQL 17. Ứng dụng sử dụng các bảng `users`, `books`, `readers`, `loans` được khai báo trong `database/init.sql`; không tự tạo lại hoặc đổi tên bảng/cột.

Kiến trúc hiện tại có Nginx làm reverse proxy duy nhất:

- **Nginx** publish `127.0.0.1:8081` ra máy hiện tại; chỉ nó nằm trên mạng `proxy_net` với `web`.
- **web** (Flask/Gunicorn) chạy nội bộ trên mạng `proxy_net` + `database_net`, **không** publish cổng host.
- **pgAdmin** ở `http://localhost:5055`; **db** (PostgreSQL 17) chỉ nội bộ trên `database_net`.
- Website ở `http://localhost:8081` trên máy hiện tại (cổng 8080 đã có dịch vụ Apache).
- Giám sát: **Prometheus** `http://localhost:9090`, **Grafana** `http://localhost:3000`; log tập trung qua Loki (xem các mục Giám sát và Log tập trung).

## Chạy website

1. Đảm bảo Docker Desktop đang chạy và các biến PostgreSQL/pgAdmin hiện có trong `.env` vẫn đúng. Trên máy mới, chỉ khi chưa có `.env`, hãy sao chép `.env.example` rồi thay tất cả giá trị `replace-with-...` bằng giá trị riêng. Không ghi đè `.env` hiện tại bằng file mẫu.
2. Khóa phiên Flask và mật khẩu DB của role ứng dụng nằm trong `.env`. Nếu còn thiếu, có thể thêm bằng PowerShell; đoạn sau tạo hai giá trị ngẫu nhiên độc lập, mỗi giá trị 32 byte, mà không in chúng:

   ```powershell
   $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
   [byte[]]$flaskBytes = New-Object byte[] 32
   [byte[]]$appBytes = New-Object byte[] 32
   $rng.GetBytes($flaskBytes)
   $rng.GetBytes($appBytes)
   $flaskKey = ([BitConverter]::ToString($flaskBytes) -replace '-', '').ToLowerInvariant()
   $appPassword = ([BitConverter]::ToString($appBytes) -replace '-', '').ToLowerInvariant()
   if (-not (Select-String -Path .env -Pattern '^FLASK_SECRET_KEY=' -Quiet)) { Add-Content .env "FLASK_SECRET_KEY=$flaskKey" }
   if (-not (Select-String -Path .env -Pattern '^APP_DB_USER=' -Quiet)) { Add-Content .env 'APP_DB_USER=library_app' }
   if (-not (Select-String -Path .env -Pattern '^APP_DB_PASSWORD=' -Quiet)) { Add-Content .env "APP_DB_PASSWORD=$appPassword" }
   [Array]::Clear($flaskBytes, 0, $flaskBytes.Length)
   [Array]::Clear($appBytes, 0, $appBytes.Length)
   $rng.Dispose()
   Remove-Variable flaskKey, appPassword, flaskBytes, appBytes, rng
   ```

   Không gửi hoặc commit `.env`. `.env.example` chỉ có giá trị minh họa cho cài đặt mới.

3. Tạo role PostgreSQL tối thiểu cho ứng dụng. Thêm `APP_DB_USER=library_app` và một `APP_DB_PASSWORD` ngẫu nhiên dài ít nhất 32 ký tự vào `.env`. Trên database đã có volume, provision role một lần trước khi khởi động web:

   ```powershell
   docker compose up -d db
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/02_init_monitoring.sql'
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/03_setup_app_role.sql'
   ```

   Hai lệnh chỉ tạo/cập nhật role và quyền; không xóa volume hoặc thay đổi dữ liệu bảng. Trên database mới, `01_init.sql`, `02_init_monitoring.sql` và `03_setup_app_role.sql` tự chạy theo thứ tự khi PostgreSQL khởi tạo volume.

4. Từ thư mục dự án, build và khởi động dịch vụ:

   ```powershell
   docker compose up -d --build
   docker compose ps
   ```

   `web` đợi `db` khỏe trước khi khởi động; `nginx` đợi `web` khỏe. Healthcheck website gọi `/healthz`, endpoint này thử kết nối PostgreSQL. Các volume `postgres_data` và `pgadmin_data` được giữ nguyên.

5. Mở [http://localhost:8081](http://localhost:8081). Toàn bộ traffic đi qua Nginx; chỉ Nginx bind vào loopback `127.0.0.1` để dùng tại máy hiện tại.

## Reverse proxy và header bảo mật

`nginx/default.conf` proxy tới `web:8080` và thêm các header:

- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
- Forwarded headers `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`.

Flask bọc `ProxyFix` với `x_for=1, x_proto=1, x_host=1, x_port=1`, chỉ tin đúng một lớp proxy. Access/error log của Nginx ghi ra stdout/stderr để Promtail thu thập.

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

Thiết lập tài khoản giám sát cho PostgreSQL (chạy một lần cho DB đã tồn tại; DB mới tự chạy script khi khởi tạo):

```powershell
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/02_init_monitoring.sql'
```

`database/init_monitoring.sql` tạo role `postgres_exporter` với `pg_monitor` (quyền đọc tối thiểu các view thống kê). Mật khẩu được đọc từ môi trường DB, không nằm trong source hoặc command line. `pg_stat_statements` được bật qua `command` của service `db`.

Role `APP_DB_USER` được `database/setup_app_role.sql` cấp `CONNECT`, `USAGE` trên schema, CRUD chỉ trên `users`, `books`, `readers`, `loans`, và quyền dùng identity sequences. Role không có superuser, `CREATEDB`, `CREATEROLE`, quyền tạo bảng/schema hay membership khác. Website chỉ nhận thông tin đăng nhập role này; tài khoản bootstrap `POSTGRES_USER` không được truyền vào web.

Kiểm tra nhanh:

```powershell
# Các target Prometheus đều UP
Invoke-RestMethod http://localhost:9090/api/v1/targets

# Số request của web
Invoke-RestMethod "http://localhost:9090/api/v1/query?query=sum(flask_http_request_total)"
```

Ghi chú Docker Desktop/WSL2: cAdvisor không lấy được tên container (chỉ có `id`, đã rút gọn thành nhãn `container_id`) và không có metrics network theo từng container (chỉ có lưu lượng theo interface Docker). Chi tiết xem `PROGRESS.md`.

## Log tập trung (Loki + Promtail)

- Loki chạy nội bộ trên `monitoring_net` và `logging_net`, không publish cổng host. Grafana truy vấn Loki qua datasource provision sẵn `Loki` (`http://loki:3100`).
- Promtail chỉ giữ các container có Compose project `library-management`, đọc Docker JSON log, và gửi đến Loki. Log có nhãn `project`, `service`, `container`, `job`; vị trí đọc được giữ trong volume `promtail_positions`.
- Dữ liệu Loki lưu trong volume `loki_data`, cấu hình retention 7 ngày. Hai volume này độc lập với volume dữ liệu PostgreSQL, pgAdmin, Grafana và Prometheus.
- Promtail dùng Docker discovery qua socket `/var/run/docker.sock` được mount read-only và đọc `/var/lib/docker/containers` read-only. Docker socket là giao diện quyền cao; chỉ chạy collector tin cậy trong project này.
- Mở Grafana `http://localhost:3000` → Explore → chọn datasource `Loki`. Một số truy vấn LogQL:

  ```logql
  {project="library-management"}
  {project="library-management", service="nginx"} |= "/__loki_probe_404"
  {project="library-management", service="nginx"} |~ "\" [45][0-9]{2} "
  sum(count_over_time({project="library-management", service=~"nginx|web|db"}[5m]))
  ```

  Truy vấn thứ hai chỉ tìm marker dùng trong demo; truy vấn thứ ba lọc status HTTP 4xx/5xx trong access log Nginx.

- Khởi động và kiểm tra:

  ```powershell
  docker compose up -d loki promtail
  docker compose restart grafana
  docker compose ps
  docker compose logs --tail 100 loki promtail
  Invoke-WebRequest http://localhost:8081/healthz
  ```

  Request health tạo một access log ở Nginx để tìm trong Explore. Loki không có cổng host; Grafana là giao diện tra cứu.
- **Vòng đời:** Grafana đánh dấu Promtail hết hỗ trợ từ 02/03/2026. Bản 3.5.8 được giữ ở đây vì giai đoạn dự án yêu cầu Promtail; nên chuyển collector sang Grafana Alloy trước khi dùng lâu dài. Xem [thông báo Promtail EOL](https://grafana.com/docs/loki/latest/send-data/promtail/) và [hướng dẫn chuyển sang Alloy](https://grafana.com/docs/alloy/latest/set-up/migrate/from-promtail/).

## Lưu ý vận hành

- `database/init.sql` của PostgreSQL chỉ chạy khi khởi tạo data directory mới. Thêm web/nginx không xóa volume hay chạy lại script lên database đã có.
- Không dùng `docker compose down -v` nếu muốn giữ dữ liệu hiện có. `docker compose down` không có `-v` vẫn giữ volume.
- Các volume `postgres_data`, `pgadmin_data`, `prometheus_data`, `grafana_data`, `loki_data` và `promtail_positions` cần được giữ; không dùng `docker compose down -v`.
- Nginx reverse proxy, Prometheus/Grafana và cấu hình Loki/Promtail đã có trong Compose. Xem `PROGRESS.md` để biết trạng thái kiểm tra runtime mới nhất.

## Hardening và kiểm chứng

- Web chạy bằng user `app`, filesystem gốc chỉ đọc, `/tmp` là tmpfs, bỏ toàn bộ Linux capabilities và bật `no-new-privileges`. Nginx bỏ toàn bộ capabilities trừ `NET_BIND_SERVICE`, `CHOWN`, `SETUID`, `SETGID` để bind cổng 80, đặt quyền thư mục tạm và hạ quyền worker; bật `no-new-privileges`.
- Web, PostgreSQL, cAdvisor và exporters không publish cổng host. pgAdmin, Prometheus, Grafana và Nginx chỉ bind loopback. Các mạng `database_net`, `proxy_net`, `monitoring_net`, `logging_net` giới hạn giao tiếp theo dịch vụ cần thiết.
- Mật khẩu DB, role ứng dụng, exporter, Grafana và khóa Flask chỉ nằm trong `.env` bị Git ignore. `.env.example` chứa giá trị mẫu. Không truyền mật khẩu PostgreSQL qua tham số command line khi chạy script provisioning.
- cAdvisor cần `privileged` và quyền đọc thông tin Docker/host để thu metrics. Promtail cần Docker socket và log container; mount socket `:ro` không biến Docker API thành giao diện chỉ đọc. Chỉ chạy các collector này trong môi trường tin cậy. Promtail đã hết hỗ trợ từ 02/03/2026; giữ theo yêu cầu đề tài và nên thay bằng Alloy khi bảo trì.
- Kết quả kiểm chứng và lệnh tái hiện nằm trong [docs/VERIFICATION.md](docs/VERIFICATION.md); kịch bản trình bày và danh sách ảnh cần chụp nằm trong [docs/DEMO.md](docs/DEMO.md).
