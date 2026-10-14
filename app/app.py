import hmac
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from getpass import getpass

import psycopg
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from psycopg import errors
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", ""),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
    MAX_CONTENT_LENGTH=1024 * 1024,
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

APP_TIMEZONE = timezone(timedelta(hours=7), name="ICT")


def local_date():
    return datetime.now(APP_TIMEZONE).date()


def connect_db():
    """Open a fresh PostgreSQL connection using the Compose or URL settings."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg.connect(
            database_url,
            options="-c timezone=" + os.environ.get("APP_TIMEZONE", "Asia/Ho_Chi_Minh"),
            row_factory=dict_row,
        )
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "library_db"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        connect_timeout=5,
        options="-c timezone=" + os.environ.get("APP_TIMEZONE", "Asia/Ho_Chi_Minh"),
        row_factory=dict_row,
    )


@app.before_request
def prepare_request():
    g.user = session.get("user")
    if request.method == "POST":
        token = session.get("csrf_token", "")
        submitted = request.form.get("csrf_token", "")
        if not token or not submitted or not hmac.compare_digest(token, submitted):
            abort(400, description="Phiên làm việc không hợp lệ. Vui lòng tải lại trang và thử lại.")


@app.context_processor
def inject_template_helpers():
    now = local_date()
    return {
        "csrf_token": lambda: session.setdefault("csrf_token", secrets.token_urlsafe(32)),
        "today": now,
        "today_label": now.strftime("%d/%m/%Y"),
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Vui lòng đăng nhập để tiếp tục.", "warning")
            return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
        return view(*args, **kwargs)

    return wrapped


def safe_next(value):
    # Only accept local paths so login cannot become an open redirect.
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return url_for("dashboard")


def field(name):
    return (request.form.get(name) or "").strip()


def validate_book_form():
    data = {
        "book_code": field("book_code"),
        "title": field("title"),
        "author": field("author"),
        "category": field("category"),
        "publisher": field("publisher"),
        "publication_year": field("publication_year"),
        "total_quantity": field("total_quantity"),
    }
    errors_by_field = {}
    limits = {"book_code": 30, "title": 200, "author": 150, "category": 100, "publisher": 150}
    for name, limit in limits.items():
        if name != "publisher" and not data[name]:
            errors_by_field[name] = "Trường này là bắt buộc."
        elif len(data[name]) > limit:
            errors_by_field[name] = f"Tối đa {limit} ký tự."
    try:
        year = int(data["publication_year"]) if data["publication_year"] else None
        if year is not None and not 1000 <= year <= 9999:
            raise ValueError
    except ValueError:
        errors_by_field["publication_year"] = "Năm xuất bản phải từ 1000 đến 9999."
        year = None
    try:
        quantity = int(data["total_quantity"])
        if quantity < 0:
            raise ValueError
    except ValueError:
        errors_by_field["total_quantity"] = "Số lượng phải là số nguyên không âm."
        quantity = None
    return data, errors_by_field, year, quantity


def validate_reader_form():
    data = {
        "reader_code": field("reader_code"),
        "full_name": field("full_name"),
        "phone": field("phone"),
        "email": field("email"),
        "address": field("address"),
    }
    errors_by_field = {}
    for name, label, limit in (
        ("reader_code", "Mã độc giả", 30),
        ("full_name", "Họ và tên", 100),
        ("phone", "Số điện thoại", 20),
        ("email", "Email", 150),
    ):
        if name in ("reader_code", "full_name") and not data[name]:
            errors_by_field[name] = f"{label} là bắt buộc."
        elif len(data[name]) > limit:
            errors_by_field[name] = f"{label} tối đa {limit} ký tự."
    if len(data["address"]) > 5000:
        errors_by_field["address"] = "Địa chỉ quá dài."
    if data["phone"] and not re.fullmatch(r"[+0-9().\-\s]{6,20}", data["phone"]):
        errors_by_field["phone"] = "Số điện thoại không hợp lệ."
    if data["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", data["email"]):
        errors_by_field["email"] = "Địa chỉ email không hợp lệ."
    return data, errors_by_field


@app.get("/healthz")
def healthz():
    try:
        with connect_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "database": "ok"}, 200
    except psycopg.Error:
        app.logger.exception("Kiểm tra kết nối cơ sở dữ liệu thất bại")
        return {"status": "unavailable", "database": "unavailable"}, 503


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = field("username")
        password = request.form.get("password", "")
        try:
            with connect_db() as conn:
                user = conn.execute(
                    "SELECT id, username, password_hash, full_name FROM users WHERE username = %s",
                    (username,),
                ).fetchone()
        except psycopg.Error:
            app.logger.exception("Không thể truy vấn tài khoản đăng nhập")
            flash("Không thể kết nối cơ sở dữ liệu. Vui lòng thử lại sau.", "error")
            return render_template("login.html", username=username), 503
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user"] = {"id": user["id"], "username": user["username"], "full_name": user["full_name"]}
            session["csrf_token"] = secrets.token_urlsafe(32)
            flash("Đăng nhập thành công.", "success")
            return redirect(safe_next(request.args.get("next") or request.form.get("next")))
        flash("Tên đăng nhập hoặc mật khẩu không đúng.", "error")
    return render_template("login.html", username=field("username") if request.method == "POST" else "")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Bạn đã đăng xuất.", "success")
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    with connect_db() as conn:
        stats = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM books) AS title_count,
                (SELECT COALESCE(SUM(total_quantity), 0) FROM books) AS copy_count,
                (SELECT COUNT(*) FROM readers) AS reader_count,
                (SELECT COUNT(*) FROM loans WHERE returned_date IS NULL) AS active_loans,
                (SELECT COUNT(*) FROM loans WHERE returned_date IS NULL AND due_date < CURRENT_DATE) AS overdue_loans
            """
        ).fetchone()
        recent_loans = conn.execute(
            """
            SELECT l.id, l.borrowed_date, l.due_date, l.returned_date,
                   b.title, r.full_name
            FROM loans l
            JOIN books b ON b.id = l.book_id
            JOIN readers r ON r.id = l.reader_id
            ORDER BY l.created_at DESC, l.id DESC
            LIMIT 6
            """
        ).fetchall()
    return render_template("dashboard.html", stats=stats, recent_loans=recent_loans)


@app.route("/books", methods=["GET", "POST"])
@login_required
def books():
    if request.method == "POST":
        data, problems, year, quantity = validate_book_form()
        if problems:
            for message in problems.values():
                flash(message, "error")
            return render_template("book_form.html", book=data, errors=problems, editing=False), 400
        try:
            with connect_db() as conn:
                conn.execute(
                    """INSERT INTO books (book_code, title, author, category, publisher, publication_year, total_quantity)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (data["book_code"], data["title"], data["author"], data["category"], data["publisher"] or None, year, quantity),
                )
            flash("Đã thêm sách.", "success")
            return redirect(url_for("books"))
        except errors.UniqueViolation:
            flash("Mã sách đã tồn tại. Vui lòng chọn mã khác.", "error")
            return render_template("book_form.html", book=data, errors={}, editing=False), 400
        except psycopg.Error:
            app.logger.exception("Không thể thêm sách")
            flash("Không thể lưu sách. Vui lòng thử lại.", "error")
            return render_template("book_form.html", book=data, errors={}, editing=False), 500
    query = field("q")
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT b.*, b.total_quantity - COUNT(l.id) FILTER (WHERE l.returned_date IS NULL) AS available_quantity
            FROM books b
            LEFT JOIN loans l ON l.book_id = b.id
            WHERE (%s = '' OR b.book_code ILIKE %s OR b.title ILIKE %s OR b.author ILIKE %s OR b.category ILIKE %s)
            GROUP BY b.id
            ORDER BY b.title, b.id
            """,
            (query, f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    return render_template("books.html", books=rows, q=query)


@app.get("/books/new")
@login_required
def new_book():
    return render_template("book_form.html", book={}, errors={}, editing=False)


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@login_required
def edit_book(book_id):
    with connect_db() as conn:
        book = conn.execute("SELECT * FROM books WHERE id = %s", (book_id,)).fetchone()
    if not book:
        abort(404)
    if request.method == "POST":
        data, problems, year, quantity = validate_book_form()
        if problems:
            for message in problems.values():
                flash(message, "error")
            data["id"] = book_id
            return render_template("book_form.html", book=data, errors=problems, editing=True), 400
        try:
            with connect_db() as conn:
                locked = conn.execute("SELECT id FROM books WHERE id = %s FOR UPDATE", (book_id,)).fetchone()
                if not locked:
                    abort(404)
                borrowed = conn.execute(
                    "SELECT COUNT(*) AS total FROM loans WHERE book_id = %s AND returned_date IS NULL",
                    (book_id,),
                ).fetchone()["total"]
                if quantity < borrowed:
                    flash(f"Tổng số cuốn không thể thấp hơn {borrowed} cuốn đang được mượn.", "error")
                    data["id"] = book_id
                    return render_template("book_form.html", book=data, errors={}, editing=True), 400
                conn.execute(
                    """UPDATE books SET book_code = %s, title = %s, author = %s, category = %s,
                       publisher = %s, publication_year = %s, total_quantity = %s WHERE id = %s""",
                    (data["book_code"], data["title"], data["author"], data["category"], data["publisher"] or None, year, quantity, book_id),
                )
            flash("Đã cập nhật thông tin sách.", "success")
            return redirect(url_for("books"))
        except errors.UniqueViolation:
            flash("Mã sách đã được sử dụng bởi sách khác.", "error")
            data["id"] = book_id
            return render_template("book_form.html", book=data, errors={}, editing=True), 400
        except psycopg.Error:
            app.logger.exception("Không thể cập nhật sách")
            flash("Không thể cập nhật sách. Vui lòng thử lại.", "error")
            return render_template("book_form.html", book=data, errors={}, editing=True), 500
    return render_template("book_form.html", book=book, errors={}, editing=True)


@app.post("/books/<int:book_id>/delete")
@login_required
def delete_book(book_id):
    try:
        with connect_db() as conn:
            result = conn.execute("DELETE FROM books WHERE id = %s", (book_id,))
            if result.rowcount == 0:
                flash("Không tìm thấy sách cần xóa.", "warning")
            else:
                flash("Đã xóa sách.", "success")
    except errors.ForeignKeyViolation:
        flash("Không thể xóa sách vì đã có lịch sử mượn tham chiếu. Hãy giữ sách trong danh mục để bảo toàn lịch sử.", "error")
    except psycopg.Error:
        app.logger.exception("Không thể xóa sách")
        flash("Không thể xóa sách. Vui lòng thử lại.", "error")
    return redirect(url_for("books"))


@app.route("/readers", methods=["GET", "POST"])
@login_required
def readers():
    if request.method == "POST":
        data, problems = validate_reader_form()
        if problems:
            for message in problems.values():
                flash(message, "error")
            return render_template("reader_form.html", reader=data, errors=problems, editing=False), 400
        try:
            with connect_db() as conn:
                conn.execute(
                    "INSERT INTO readers (reader_code, full_name, phone, email, address) VALUES (%s, %s, %s, %s, %s)",
                    (data["reader_code"], data["full_name"], data["phone"] or None, data["email"] or None, data["address"] or None),
                )
            flash("Đã thêm độc giả.", "success")
            return redirect(url_for("readers"))
        except errors.UniqueViolation:
            flash("Mã độc giả đã tồn tại. Vui lòng chọn mã khác.", "error")
            return render_template("reader_form.html", reader=data, errors={}, editing=False), 400
        except psycopg.Error:
            app.logger.exception("Không thể thêm độc giả")
            flash("Không thể lưu độc giả. Vui lòng thử lại.", "error")
            return render_template("reader_form.html", reader=data, errors={}, editing=False), 500
    query = field("q")
    with connect_db() as conn:
        rows = conn.execute(
            """SELECT * FROM readers
               WHERE (%s = '' OR reader_code ILIKE %s OR full_name ILIKE %s OR phone ILIKE %s OR email ILIKE %s)
               ORDER BY full_name, id""",
            (query, f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    return render_template("readers.html", readers=rows, q=query)


@app.get("/readers/new")
@login_required
def new_reader():
    return render_template("reader_form.html", reader={}, errors={}, editing=False)


@app.route("/readers/<int:reader_id>/edit", methods=["GET", "POST"])
@login_required
def edit_reader(reader_id):
    with connect_db() as conn:
        reader = conn.execute("SELECT * FROM readers WHERE id = %s", (reader_id,)).fetchone()
    if not reader:
        abort(404)
    if request.method == "POST":
        data, problems = validate_reader_form()
        if problems:
            for message in problems.values():
                flash(message, "error")
            data["id"] = reader_id
            return render_template("reader_form.html", reader=data, errors=problems, editing=True), 400
        try:
            with connect_db() as conn:
                conn.execute(
                    """UPDATE readers SET reader_code = %s, full_name = %s, phone = %s, email = %s, address = %s
                       WHERE id = %s""",
                    (data["reader_code"], data["full_name"], data["phone"] or None, data["email"] or None, data["address"] or None, reader_id),
                )
            flash("Đã cập nhật thông tin độc giả.", "success")
            return redirect(url_for("readers"))
        except errors.UniqueViolation:
            flash("Mã độc giả đã được sử dụng bởi người khác.", "error")
            data["id"] = reader_id
            return render_template("reader_form.html", reader=data, errors={}, editing=True), 400
        except psycopg.Error:
            app.logger.exception("Không thể cập nhật độc giả")
            flash("Không thể cập nhật độc giả. Vui lòng thử lại.", "error")
            return render_template("reader_form.html", reader=data, errors={}, editing=True), 500
    return render_template("reader_form.html", reader=reader, errors={}, editing=True)


@app.post("/readers/<int:reader_id>/delete")
@login_required
def delete_reader(reader_id):
    try:
        with connect_db() as conn:
            result = conn.execute("DELETE FROM readers WHERE id = %s", (reader_id,))
            if result.rowcount == 0:
                flash("Không tìm thấy độc giả cần xóa.", "warning")
            else:
                flash("Đã xóa độc giả.", "success")
    except errors.ForeignKeyViolation:
        flash("Không thể xóa độc giả vì đã có lịch sử mượn tham chiếu. Hãy giữ hồ sơ để bảo toàn lịch sử.", "error")
    except psycopg.Error:
        app.logger.exception("Không thể xóa độc giả")
        flash("Không thể xóa độc giả. Vui lòng thử lại.", "error")
    return redirect(url_for("readers"))


@app.route("/loans", methods=["GET", "POST"])
@login_required
def loans():
    if request.method == "POST":
        try:
            reader_id = int(field("reader_id"))
            book_id = int(field("book_id"))
            borrowed_date = date.fromisoformat(field("borrowed_date"))
            due_date = date.fromisoformat(field("due_date"))
        except (ValueError, TypeError):
            flash("Vui lòng chọn độc giả, sách và ngày mượn/trả hợp lệ.", "error")
            return redirect(url_for("loans"))
        note = field("note")
        if len(note) > 2000:
            flash("Ghi chú tối đa 2000 ký tự.", "error")
            return redirect(url_for("loans"))
        if borrowed_date > local_date():
            flash("Ngày mượn không được ở trong tương lai.", "error")
            return redirect(url_for("loans"))
        if due_date < borrowed_date:
            flash("Ngày hẹn trả không được trước ngày mượn.", "error")
            return redirect(url_for("loans"))
        try:
            with connect_db() as conn:
                book = conn.execute(
                    "SELECT id, total_quantity, title FROM books WHERE id = %s FOR UPDATE",
                    (book_id,),
                ).fetchone()
                if not book:
                    flash("Không tìm thấy sách đã chọn.", "error")
                    return redirect(url_for("loans"))
                reader = conn.execute("SELECT id FROM readers WHERE id = %s", (reader_id,)).fetchone()
                if not reader:
                    flash("Không tìm thấy độc giả đã chọn.", "error")
                    return redirect(url_for("loans"))
                borrowed = conn.execute(
                    "SELECT COUNT(*) AS total FROM loans WHERE book_id = %s AND returned_date IS NULL",
                    (book_id,),
                ).fetchone()["total"]
                if borrowed >= book["total_quantity"]:
                    flash(f"Sách ‘{book['title']}’ đã được mượn hết.", "error")
                    return redirect(url_for("loans"))
                conn.execute(
                    "INSERT INTO loans (reader_id, book_id, borrowed_date, due_date, note) VALUES (%s, %s, %s, %s, %s)",
                    (reader_id, book_id, borrowed_date, due_date, note or None),
                )
            flash("Đã ghi nhận lượt mượn.", "success")
        except psycopg.Error:
            app.logger.exception("Không thể tạo lượt mượn")
            flash("Không thể tạo lượt mượn. Vui lòng thử lại.", "error")
        return redirect(url_for("loans"))
    with connect_db() as conn:
        book_rows = conn.execute(
            """SELECT b.id, b.title, b.book_code, b.total_quantity - COUNT(l.id) FILTER (WHERE l.returned_date IS NULL) AS available_quantity
               FROM books b LEFT JOIN loans l ON l.book_id = b.id
               GROUP BY b.id ORDER BY b.title"""
        ).fetchall()
        reader_rows = conn.execute("SELECT id, reader_code, full_name FROM readers ORDER BY full_name").fetchall()
        loan_rows = conn.execute(
            """SELECT l.*, b.title AS book_title, b.book_code, r.full_name AS reader_name, r.reader_code,
                      (l.returned_date IS NULL AND l.due_date < CURRENT_DATE) AS is_overdue
               FROM loans l JOIN books b ON b.id = l.book_id JOIN readers r ON r.id = l.reader_id
               ORDER BY (l.returned_date IS NULL) DESC, l.borrowed_date DESC, l.id DESC"""
        ).fetchall()
    return render_template(
        "loans.html",
        books=book_rows,
        readers=reader_rows,
        loans=loan_rows,
        today=local_date().isoformat(),
        due_date_default=(local_date() + timedelta(days=14)).isoformat(),
    )


@app.post("/loans/<int:loan_id>/return")
@login_required
def return_loan(loan_id):
    with connect_db() as conn:
        updated = conn.execute(
            "UPDATE loans SET returned_date = CURRENT_DATE WHERE id = %s AND returned_date IS NULL RETURNING id",
            (loan_id,),
        ).fetchone()
        if updated:
            flash("Đã ghi nhận trả sách.", "success")
        else:
            existing = conn.execute("SELECT id FROM loans WHERE id = %s", (loan_id,)).fetchone()
            flash("Lượt mượn đã được trả trước đó." if existing else "Không tìm thấy lượt mượn.", "warning")
    return redirect(url_for("loans"))


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", title="Yêu cầu không hợp lệ", message=getattr(error, "description", "Dữ liệu gửi lên không hợp lệ.")), 400


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", title="Không tìm thấy trang", message="Đường dẫn hoặc dữ liệu bạn yêu cầu không tồn tại."), 404


@app.cli.command("create-admin")
def create_admin():
    """Interactively create an administrator without putting the password in shell history."""
    username = input("Tên đăng nhập quản trị (3–50 ký tự): ").strip()
    full_name = input("Họ và tên: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", username):
        raise SystemExit("Tên đăng nhập chỉ gồm chữ, số, dấu chấm, gạch dưới hoặc gạch ngang; dài 3–50 ký tự.")
    if not full_name or len(full_name) > 100:
        raise SystemExit("Họ và tên là bắt buộc và tối đa 100 ký tự.")
    password = getpass("Mật khẩu (ít nhất 12 ký tự): ")
    confirmation = getpass("Nhập lại mật khẩu: ")
    if len(password) < 12:
        raise SystemExit("Mật khẩu phải có ít nhất 12 ký tự.")
    if password != confirmation:
        raise SystemExit("Hai mật khẩu không khớp.")
    try:
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name) VALUES (%s, %s, %s)",
                (username, generate_password_hash(password), full_name),
            )
    except errors.UniqueViolation:
        raise SystemExit("Tên đăng nhập đã tồn tại.") from None
    except psycopg.Error as exc:
        raise SystemExit("Không thể tạo tài khoản. Hãy kiểm tra kết nối cơ sở dữ liệu.") from exc
    print(f"Đã tạo tài khoản quản trị ‘{username}’.")
