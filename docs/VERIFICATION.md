# Kết quả hardening và kiểm thử

Ngày kiểm tra: **2026-10-14**. Môi trường: Windows, Docker Desktop/WSL2, Docker Compose v5.5.1. Các lệnh dưới đây không chứa mật khẩu hoặc khóa.

## Đối chiếu tiêu chí

| Tiêu chí | Cấu hình/minh chứng | Kết quả thực tế |
|---|---|---|
| Bảng đúng đề tài | **database/init.sql**: **users**, **books**, **readers**, **loans**; không đổi tên bảng/cột | Đạt |
| Web không chạy root | **app/Dockerfile** khai báo **USER app:app**; kiểm tra **docker compose exec web id** | **app:app**; root filesystem read-only |
| Tách mạng, không publish cổng thừa | **database_net**, **proxy_net**, **monitoring_net**, **logging_net**; **docker compose ps** | Web, DB, cAdvisor, postgres-exporter, nginx-exporter không publish cổng host; UI cần thiết chỉ bind **127.0.0.1** |
| PostgreSQL least privilege | **database/setup_app_role.sql**; Flask dùng **PGUSER/PGPASSWORD** | Runtime **current_user=library_app**; không superuser/CREATEDB/CREATEROLE/BYPASSRLS; CRUD bốn bảng và identity sequences đạt; không tạo schema, bảng hoặc TRUNCATE |
| Exporter DB least privilege | **database/init_monitoring.sql** cấp **pg_monitor** | **postgres_exporter** không superuser/CREATEDB/CREATEROLE; kiểm tra role và metrics thành công |
| Secrets ngoài Git | **.gitignore**, **.env.example**, Compose environment | **.env** bị ignore và không nằm trong **git ls-files**; file mẫu chỉ có giá trị mẫu; web không nhận biến bootstrap **POSTGRES_USER/POSTGRES_PASSWORD** |
| Security headers và proxy | **nginx/default.conf**, ProxyFix tin một proxy | **/login** qua Nginx trả **X-Content-Type-Options: nosniff**, **X-Frame-Options: DENY**, **Referrer-Policy: strict-origin-when-cross-origin**; cấu hình Nginx test thành công |
| Container hardening | **docker-compose.yml** | Web: **read_only**, **/tmp** tmpfs, **cap_drop: ALL**, **no-new-privileges**; exporters: read-only rootfs/tmpfs, bỏ capabilities, no-new-privileges; Nginx bỏ toàn bộ capabilities trừ các quyền cần để bind cổng, chown temp và hạ quyền worker |
| Đăng nhập, logout, bảo vệ trang, CSRF, hash | **app/app.py**, **tests/verify_flows.py** | Tất cả đạt trong database scratch; admin CLI được thử trên terminal tương tác, mật khẩu không xuất hiện trong output |
| Sách/độc giả và mượn/trả | **tests/verify_flows.py** | Thêm/sửa/tìm; mượn còn hàng; từ chối hết hàng; khóa hàng tranh cuốn cuối chỉ một thành công; trả lần hai bị từ chối; chặn giảm số lượng; xóa hồ sơ có lịch sử bị từ chối và dữ liệu giữ nguyên |
| Prometheus/Grafana | Prometheus targets API và Grafana datasource proxy | 5/5 target UP; Grafana trả **up=5**, **pg_up=1**, có series **flask_http_request_total**; datasource Prometheus/Loki và dashboard **Library Monitoring** đã provision |
| Loki/LogQL | Grafana datasource proxy tới Loki | Có log mới từ Nginx, Flask/Gunicorn và PostgreSQL; marker trả 1 entry; bộ lọc mã HTTP trả một 404 thật; truy vấn đếm có dữ liệu |
| Triển khai mới | Project **library-hardening-fresh-20261014**, volume/cổng riêng | **docker compose up -d --build** thành công; init 5 sách/3 độc giả; role app/exporter, admin CLI, pgAdmin, Grafana provisioning và 5 target được xác nhận |

## Kết quả runtime

- Project hiện tại **library-management**: **docker compose config --quiet**, **docker compose up -d --build**, healthcheck DB/web/Nginx và **docker compose exec nginx nginx -t** đều đạt. **/healthz** trả **status=ok**, **database=ok**; CSS và trang đăng nhập trả 200.
- DB hiện tại được provision thêm role/grant, không sửa dữ liệu bảng. Số bản ghi trước và sau là **6 sách, 4 độc giả, 1 lượt mượn, 1 tài khoản**. Website sau đó kết nối bằng **library_app**.
- Sáu volume production vẫn hiện diện: **postgres_data**, **pgadmin_data**, **prometheus_data**, **grafana_data**, **loki_data**, **promtail_positions**.
- Prometheus: **cadvisor**, **nginx-exporter**, **postgres-exporter**, **prometheus**, **web** đều **UP**. Grafana API truy vấn **up**, **pg_up**, **flask_http_request_total** thành công. pgAdmin login page trả 200.
- Web container có user **app:app**, root filesystem read-only, cap drop ALL, no-new-privileges và không publish port. Nginx worker chạy user **nginx**; master chạy root với tập capability rút gọn. Nginx root filesystem chưa đặt read-only vì Nginx cần tạo và chown thư mục temp/cache lúc khởi động; đã giữ các capability cần thiết ở mức tối thiểu.

### LogQL đã chạy

Các truy vấn sau được gửi qua datasource Loki của Grafana trong cửa sổ 15 phút. Trước đó đã gọi **GET /__loki_probe_404** qua Nginx; response thực tế là **404**.

~~~logql
{project="library-management"}
{project="library-management", service="nginx"} |= "/__loki_probe_404"
{project="library-management", service="nginx"} |~ "\" [45][0-9]{2} "
sum(count_over_time({project="library-management", service=~"nginx|web|db"}[5m]))
~~~

Truy vấn thứ hai khớp một marker URI dành cho demo. Truy vấn thứ ba lọc status 400–599 trong access log Nginx; lần chạy này khớp một HTTP 404 thật. Không tạo lỗi HTTP 5xx trên website production. Truy vấn xem log được giới hạn ở 200 entries trong lần lấy mẫu; truy vấn đếm trả dữ liệu. Truy vấn riêng trong 60 phút trả 27 entry **db**; **web** và **nginx** mỗi loại chạm giới hạn lấy mẫu 500 entries.

### Database mới và test nghiệp vụ

- Stack scratch cuối cùng dùng project riêng **library-hardening-fresh-20261014** và cổng **18281**, **15505**, **19091**, **13001**. Lượt **up -d --build** hoàn tất, DB/web/Nginx healthy; pgAdmin trả 200; Grafana API healthy, provision đủ datasource/dashboard; Prometheus 5/5 UP.
- Init DB tạo 5 sách, 3 độc giả, 0 lượt mượn và 0 tài khoản. Kiểm tra app role có CRUD/sequence cần thiết, không quyền elevated; exporter có **pg_monitor** và không quyền elevated.
- **flask --app app create-admin** được nhập qua terminal tương tác; mật khẩu được ẩn và chỉ tạo trong database test. Bộ **tests/verify_flows.py** chạy trên database này và tất cả nhóm kiểm tra nghiệp vụ, quyền DB, login/CSRF, proxy/CSS/headers đều PASS. Test records có prefix **VERIFY-**.
- Hai project test đã dừng bằng **docker compose down** không có **-v**. Mỗi project giữ sáu named volumes riêng. Không volume production hoặc project Docker khác bị xóa/dừng.

## Lệnh kiểm tra lại trên project hiện tại

~~~powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec nginx nginx -t
Invoke-RestMethod http://localhost:8081/healthz
(Invoke-RestMethod http://localhost:9090/api/v1/targets).data.activeTargets | Select-Object labels, health
docker compose exec -T web id
docker compose exec -T web python -c "from app import connect_db; c=connect_db(); print(c.execute('select current_user').fetchone()); c.close()"
~~~

### Provision DB hiện có

**.env** cần có **APP_DB_USER** và **APP_DB_PASSWORD** ngẫu nhiên dài ít nhất 32 ký tự. Hai script dưới đây đọc password từ environment của container DB, không đưa secret lên command line:

~~~powershell
docker compose up -d db
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/02_init_monitoring.sql'
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/03_setup_app_role.sql'
docker compose up -d --build web
~~~

Database mới tự chạy ba file **01_init.sql**, **02_init_monitoring.sql**, **03_setup_app_role.sql** theo thứ tự. Không xóa volume để provision.

### Dựng stack mới cô lập

Đoạn PowerShell sau tạo khóa ngẫu nhiên trong bộ nhớ, dùng Compose project/volume riêng và tránh cổng production. Chọn một tên project/cổng chưa dùng nếu chạy lại:

~~~powershell
function New-TestSecret {
  $random = [Security.Cryptography.RandomNumberGenerator]::Create()
  [byte[]]$buffer = New-Object byte[] 32
  $random.GetBytes($buffer)
  $secret = ([BitConverter]::ToString($buffer) -replace '-', '').ToLowerInvariant()
  [Array]::Clear($buffer, 0, $buffer.Length)
  $random.Dispose()
  return $secret
}
$project = 'library-hardening-verify-demo'
$env:POSTGRES_DB = 'library_verify'
$env:POSTGRES_USER = 'library_admin_verify'
$env:POSTGRES_PASSWORD = New-TestSecret
$env:APP_DB_USER = 'library_app_verify'
$env:APP_DB_PASSWORD = New-TestSecret
$env:PG_EXPORTER_PASSWORD = New-TestSecret
$env:PGADMIN_DEFAULT_EMAIL = 'verification@example.com'
$env:PGADMIN_DEFAULT_PASSWORD = New-TestSecret
$env:FLASK_SECRET_KEY = New-TestSecret
$env:GRAFANA_ADMIN_PASSWORD = New-TestSecret
$env:WEB_HOST_PORT = '18281'
$env:PGADMIN_HOST_PORT = '15505'
$env:PROMETHEUS_HOST_PORT = '19091'
$env:GRAFANA_HOST_PORT = '13001'
docker compose -p $project up -d --build
docker compose -p $project ps
docker compose -p $project exec web flask --app app create-admin
~~~

Sau khi tạo admin, có thể chạy bộ test chỉ trên stack scratch. Prompt dưới đây nhận password ẩn rồi truyền giá trị qua environment, không đặt trong command text:

~~~powershell
$secure = Read-Host 'Mật khẩu admin test' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $env:VERIFY_ADMIN_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
Get-Content -Raw tests\verify_flows.py | docker compose -p $project exec -T -e VERIFY_ADMIN_PASSWORD web python -
$env:VERIFY_ADMIN_PASSWORD = $null
~~~

Sau kiểm tra, dừng đúng project scratch bằng **docker compose -p $project down**; không thêm **-v** nếu cần giữ test volume.

## Ngoại lệ và giới hạn

- cAdvisor vẫn **privileged** và mount metadata host/Docker để thu container metrics. Promtail cần Docker socket; mount **:ro** không biến API socket thành quyền chỉ đọc. Đây là các ngoại lệ quyền cao của monitoring/log collector.
- PostgreSQL, Prometheus, Grafana, Loki và Promtail cần đường ghi dữ liệu/position trên volume; web/exporter phù hợp hơn với root filesystem read-only.
- Không chạy CRUD test trên dữ liệu production. Đã có ảnh chụp trực quan một số trang web và màn hình giám sát; danh sách ảnh an toàn để chia sẻ cùng các minh chứng còn thiếu được ghi trong [DEMO.md](DEMO.md). Ảnh không xác nhận các kiểm thử nghiệp vụ chưa chạy. Không phát sinh HTTP 5xx trong production; regex LogQL được xác nhận bằng response 404 thật.
- Promtail đã EOL ngày 02/03/2026; giữ theo yêu cầu đề tài. Xem [Grafana Promtail EOL](https://grafana.com/docs/loki/latest/send-data/promtail/) và lên kế hoạch chuyển sang Alloy.
