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

## Ảnh cần chụp cuối cùng

- Trang tổng quan website sau đăng nhập, các số liệu nhìn rõ.
- Bảng sách thể hiện số lượng còn; bảng độc giả.
- Sổ mượn trả thể hiện ít nhất một lượt đang mượn và một lượt đã trả.
- pgAdmin hiển thị database **library_db** và bốn bảng nghiệp vụ.
- Response headers của **/login** qua Nginx hoặc kết quả **curl -I**.
- **docker compose ps** cho thấy health trạng thái DB/web/Nginx và các cổng chỉ bind loopback.
- Prometheus **Targets** với 5 target UP.
- Dashboard **Library Monitoring** có dữ liệu container, web, database.
- Grafana Explore: marker URI và truy vấn regex status 4xx/5xx có kết quả 404.
- Terminal minh họa **id** của web user và role PostgreSQL runtime cùng các cờ elevated **false**.

Chưa có ảnh nào được tạo hoặc chụp trong lần kiểm chứng này. Danh sách trên là danh sách ảnh cần chụp thật khi chuẩn bị báo cáo/demo.
