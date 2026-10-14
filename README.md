# Hệ thống quản lý thư viện

Website nội bộ dùng Flask, Jinja, CSS và PostgreSQL 17. Ứng dụng sử dụng các bảng `users`, `books`, `readers`, `loans` được khai báo trong `database/init.sql`; không tự tạo lại hoặc đổi tên bảng/cột. pgAdmin tiếp tục ở `http://localhost:5055`. Website dùng `http://localhost:8081` trên máy hiện tại vì cổng 8080 đã có dịch vụ Apache; có thể đặt `WEB_PORT=8080` trong `.env` khi cổng này trống.

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

   `web` đợi `db` khỏe trước khi khởi động. Healthcheck website gọi `/healthz`, endpoint này thử kết nối PostgreSQL. Các volume `postgres_data` và `pgadmin_data` được giữ nguyên.

4. Mở [http://localhost:8081](http://localhost:8081). Website chỉ bind vào loopback `127.0.0.1` để dùng tại máy hiện tại. `WEB_PORT` đổi cổng host nếu cần.

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
- Xem trạng thái dịch vụ và healthcheck bằng `docker compose ps`; kiểm tra nhật ký web bằng `docker compose logs web`.
- Có thể kiểm tra trực tiếp endpoint DB bằng `Invoke-RestMethod http://localhost:8081/healthz`; khi khỏe, kết quả có `status: ok` và `database: ok`.

Các thao tác thêm, sửa, xóa, mượn, trả và đăng xuất dùng POST có CSRF token. Đăng nhập yêu cầu mật khẩu băm, không có tài khoản hoặc mật khẩu mặc định trong source. Các yêu cầu mượn cùng sách được tuần tự hóa bằng khóa hàng PostgreSQL trong transaction, sau đó mới đếm lượt chưa trả và tạo lượt mới.

## Lưu ý vận hành

- `database/init.sql` của PostgreSQL chỉ chạy khi khởi tạo data directory mới. Thêm web không xóa volume hay chạy lại script lên database đã có.
- Không dùng `docker compose down -v` nếu muốn giữ dữ liệu hiện có. `docker compose down` không có `-v` vẫn giữ volume.
- Giai đoạn này chỉ thêm website và dịch vụ Flask; chưa cấu hình Nginx, Prometheus/Grafana, Loki/Promtail.
