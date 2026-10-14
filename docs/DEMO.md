# Kịch bản demo

Kịch bản này dùng giao diện hiện có và các công cụ runtime của project. Không đưa password, token, khóa phiên hoặc dữ liệu cá nhân vào ảnh chụp. Nếu cần thao tác thêm/sửa/xóa trong buổi demo, dùng database scratch với project/cổng/volume riêng; không thử luồng phá hủy trên dữ liệu production.

## Trình tự trình bày

### 1. Website thư viện

1. Mở [http://localhost:8081](http://localhost:8081), đăng nhập bằng admin đã tạo.
2. Trình bày trang tổng quan: đầu sách, tổng số cuốn, độc giả, lượt đang mượn và quá hạn.
3. Mở **Sách** và **Độc giả** để cho thấy tìm kiếm, thông tin và thao tác CRUD.
4. Mở **Mượn và trả**; giải thích mỗi lượt là một cuốn, số còn lại bằng tổng số trừ lượt chưa trả, lịch sử vẫn giữ sau khi trả.
5. Với database scratch, trình diễn hết hàng, trả hai lần, giảm tổng số dưới số đang mượn và xóa hồ sơ có lịch sử. Thông báo trả bằng tiếng Việt.
6. Có thể tạo admin từ terminal bằng lệnh sau; nhập password tại prompt ẩn. Không dùng tài khoản mặc định.

~~~powershell
docker compose exec web flask --app app create-admin
~~~

### 2. pgAdmin và PostgreSQL

- Mở [http://localhost:5055](http://localhost:5055), đăng nhập bằng thông tin pgAdmin hiện có.
- Kết nối PostgreSQL bằng hostname **db** và port **5432** trên Docker network; xem database và các bảng **users**, **books**, **readers**, **loans**.
- Role website là **APP_DB_USER** trong **.env**, không phải tài khoản bootstrap/superuser. Không trình chiếu giá trị password trong **.env**.

### 3. Nginx và hardening

~~~powershell
docker compose exec nginx nginx -t
Invoke-WebRequest http://localhost:8081/login -Method Head
docker compose exec -T web id
docker compose exec -T web python -c "from app import connect_db; c=connect_db(); print(c.execute('select current_user').fetchone()); c.close()"
docker compose ps
~~~

Trình bày ba security headers của response, user **app** trong web, role runtime **library_app**, web/DB/exporter không publish cổng host và các network riêng. cAdvisor chạy **privileged**; Promtail có quyền đọc Docker socket/logs để thu thập telemetry.

### 4. Prometheus và Grafana

- Mở Prometheus [http://localhost:9090](http://localhost:9090) → **Status → Targets**, xác nhận 5 target UP.
- Mở Grafana [http://localhost:3000](http://localhost:3000), chọn dashboard **Library Monitoring**.
- Trình bày biểu đồ container, web và database. Có thể chạy các truy vấn Prometheus **up**, **pg_up**, **flask_http_request_total**.

### 5. Loki và LogQL

Mở Grafana → **Explore** → datasource **Loki**. Dùng:

~~~logql
{project="library-management"}
{project="library-management", service="nginx"} |= "/__loki_probe_404"
{project="library-management", service="nginx"} |~ "\" [45][0-9]{2} "
sum(count_over_time({project="library-management", service=~"nginx|web|db"}[5m]))
~~~

Truy vấn marker tìm URI demo cố định. Truy vấn regex thứ ba lọc status HTTP 4xx/5xx; lần kiểm chứng thực tế khớp một response 404 được phát sinh qua Nginx. Truy vấn cuối đếm log theo thời gian.

Để tạo một marker mới:

~~~powershell
try { Invoke-WebRequest http://localhost:8081/__loki_probe_404 -UseBasicParsing } catch { $_.Exception.Response.StatusCode.value__ }
~~~

Promtail chỉ đọc container thuộc Compose project **library-management**. Promtail đã hết hỗ trợ từ 02/03/2026; giữ theo yêu cầu đề tài, cần thay bằng Grafana Alloy khi bảo trì.

## Ảnh minh chứng hiện có và còn thiếu

Ảnh trong `docs/screenshots` đã được xem trực tiếp. Những ảnh được commit là ảnh PNG hợp lệ; ảnh nguồn AVIF gắn nhầm đuôi `.png` đã được chuyển định dạng không đổi nội dung. Danh sách ảnh được đưa lên repo:

- `02-quan-ly-sach.png`: bảng sách và số lượng còn.
- `04-muon-tra.png`: sổ mượn trả, hiện chỉ thấy lượt đã trả.
- `05-pgadmin.png`: database `library_db` và bốn bảng nghiệp vụ.
- `06-docker-compose.png`: terminal tạo admin và trạng thái Compose; phần ánh xạ cổng không đọc rõ.
- `07-prometheus-targets.png`: 5 target Prometheus UP.
- `08-grafana-container.png`, `09-grafana-web.png`, `10-grafana-database.png`: dashboard Library Monitoring.
- `11-loki-logs.png`, `12-loki-404.png`, `13-loki-count.png`: Explore log, marker URI và truy vấn đếm theo thời gian.
- `15-web-non-root.png`: UID/GID của tiến trình web.
- `16-github-commits.png`: lịch sử GitHub trước commit ảnh này.

Các ảnh còn lại được giữ ngoài commit: `01-tong-quan.png` trùng hoàn toàn với ảnh sách; `03-doc-gia.png` hiển thị thông tin liên hệ; `14-nginx-headers.avif` hiển thị giá trị cookie phiên trong header `Set-Cookie`. Không chia sẻ ảnh chứa thông tin này.

Minh chứng còn thiếu hoặc chưa đủ:

- Trang tổng quan sau đăng nhập: chưa có ảnh.
- Bảng độc giả: chưa có ảnh an toàn để chia sẻ.
- Sổ mượn trả có cả lượt đang mượn và đã trả: ảnh hiện tại chỉ cho thấy lượt đã trả.
- Security headers Nginx: chưa có ảnh an toàn; chụp lại và che giá trị cookie trước khi chia sẻ.
- Compose health và ánh xạ cổng loopback đọc rõ: ảnh hiện có chưa thể hiện rõ cột cổng.
- Grafana Explore lọc status HTTP 4xx/5xx thực tế có kết quả: ảnh marker URI không thay thế truy vấn lọc status.
- Terminal thể hiện role PostgreSQL runtime và các cờ elevated đều `false`: chưa có ảnh.

Ảnh chỉ là minh chứng trực quan cho nội dung thấy được trên màn hình; chúng không thay thế các kiểm thử nghiệp vụ và kiểm tra cấu hình được ghi trong [VERIFICATION.md](VERIFICATION.md).
