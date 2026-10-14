BEGIN;

-- Tài khoản đăng nhập website.
-- Mật khẩu sẽ được ứng dụng mã hóa trước khi lưu.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Danh mục sách.
-- Số lượng còn có thể mượn sẽ tính từ tổng số và lượt chưa trả.
CREATE TABLE IF NOT EXISTS books (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    book_code VARCHAR(30) NOT NULL UNIQUE,
    title VARCHAR(200) NOT NULL,
    author VARCHAR(150) NOT NULL,
    category VARCHAR(100) NOT NULL,
    publisher VARCHAR(150),
    publication_year INTEGER
        CHECK (publication_year BETWEEN 1000 AND 9999),
    total_quantity INTEGER NOT NULL DEFAULT 1
        CHECK (total_quantity >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Độc giả.
CREATE TABLE IF NOT EXISTS readers (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reader_code VARCHAR(30) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(150),
    address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Lịch sử mượn và trả sách.
-- returned_date để trống nghĩa là chưa trả.
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reader_id INTEGER NOT NULL
        REFERENCES readers(id) ON DELETE RESTRICT,
    book_id INTEGER NOT NULL
        REFERENCES books(id) ON DELETE RESTRICT,
    borrowed_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE NOT NULL,
    returned_date DATE,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (due_date >= borrowed_date),
    CHECK (
        returned_date IS NULL
        OR returned_date >= borrowed_date
    )
);

CREATE INDEX IF NOT EXISTS idx_loans_reader
    ON loans(reader_id);

CREATE INDEX IF NOT EXISTS idx_loans_book
    ON loans(book_id);

CREATE INDEX IF NOT EXISTS idx_loans_due_date
    ON loans(due_date)
    WHERE returned_date IS NULL;

-- Dữ liệu sách mẫu.
INSERT INTO books (
    book_code, title, author, category,
    publisher, publication_year, total_quantity
)
VALUES
    ('S001', 'Dế Mèn phiêu lưu ký', 'Tô Hoài',
     'Văn học', 'Kim Đồng', 2020, 5),
    ('S002', 'Lão Hạc', 'Nam Cao',
     'Văn học', 'Văn học', 2021, 4),
    ('S003', 'Tắt đèn', 'Ngô Tất Tố',
     'Văn học', 'Văn học', 2020, 3),
    ('S004', 'Nhập môn lập trình Python', 'Nhóm biên soạn',
     'Công nghệ thông tin', NULL, 2024, 6),
    ('S005', 'Cơ sở dữ liệu căn bản', 'Nhóm biên soạn',
     'Công nghệ thông tin', NULL, 2023, 4)
ON CONFLICT (book_code) DO NOTHING;

-- Độc giả mẫu: thông tin giả lập để demo.
INSERT INTO readers (
    reader_code, full_name, phone, email, address
)
VALUES
    ('DG001', 'Nguyễn Minh Anh', '0900000001',
     'minhanh@example.com', 'Hà Nội'),
    ('DG002', 'Trần Thu Hà', '0900000002',
     'thuha@example.com', 'Đà Nẵng'),
    ('DG003', 'Lê Quốc Huy', '0900000003',
     'quochuy@example.com', 'TP. Hồ Chí Minh')
ON CONFLICT (reader_code) DO NOTHING;

COMMIT;

-- Kích hoạt pg_stat_statements để postgres_exporter thu thập metrics hoạt động
-- truy vấn. shared_preload_libraries được đặt qua `command` trong docker-compose.yml.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Kiểm tra dữ liệu vừa tạo.
SELECT 'books' AS table_name, COUNT(*) AS total FROM books
UNION ALL
SELECT 'readers', COUNT(*) FROM readers
UNION ALL
SELECT 'loans', COUNT(*) FROM loans
UNION ALL
SELECT 'users', COUNT(*) FROM users;