"""Destructive-flow integration checks; run only against an isolated test database."""

import re
import threading
import uuid
import os
from getpass import getpass
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from http.cookiejar import CookieJar

from app import app, connect_db


ADMIN_USER = "verify_admin"
ADMIN_PASSWORD = os.environ.get("VERIFY_ADMIN_PASSWORD") or getpass("Verification admin password: ")
SUFFIX = uuid.uuid4().hex[:10].upper()
BOOK_CODE = f"VERIFY-B-{SUFFIX}"
READER_CODE = f"VERIFY-R-{SUFFIX}"
TODAY = date.today()
PASSED = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def csrf_token(client, path):
    response = client.get(path)
    check(response.status_code == 200, f"GET {path} returned {response.status_code}")
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    check(match is not None, f"No CSRF field found on {path}")
    return match.group(1).decode("ascii")


def login_client():
    client = app.test_client()
    token = csrf_token(client, "/login")
    response = client.post(
        "/login",
        data={"csrf_token": token, "username": ADMIN_USER, "password": ADMIN_PASSWORD},
        follow_redirects=True,
    )
    check(response.status_code == 200, "Admin login failed")
    check(client.get("/").status_code == 200, "Authenticated dashboard was unavailable")
    return client


def book_form(code, title, quantity):
    return {
        "book_code": code,
        "title": title,
        "author": "Verification Author",
        "category": "Verification",
        "publisher": "Test Publisher",
        "publication_year": "2024",
        "total_quantity": str(quantity),
    }


def reader_form(code, full_name):
    return {
        "reader_code": code,
        "full_name": full_name,
        "phone": "0900000123",
        "email": f"{code.lower()}@example.invalid",
        "address": "Marked integration test record",
    }


def create_book(client, code, title, quantity):
    token = csrf_token(client, "/books")
    response = client.post("/books", data={**book_form(code, title, quantity), "csrf_token": token})
    check(response.status_code == 302, f"Adding book returned {response.status_code}")
    with connect_db() as conn:
        return conn.execute("SELECT id FROM books WHERE book_code = %s", (code,)).fetchone()["id"]


def create_reader(client, code, full_name):
    token = csrf_token(client, "/readers")
    response = client.post("/readers", data={**reader_form(code, full_name), "csrf_token": token})
    check(response.status_code == 302, f"Adding reader returned {response.status_code}")
    with connect_db() as conn:
        return conn.execute("SELECT id FROM readers WHERE reader_code = %s", (code,)).fetchone()["id"]


def submit_loan(client, reader_id, book_id):
    token = csrf_token(client, "/loans")
    return client.post(
        "/loans",
        data={
            "csrf_token": token,
            "reader_id": str(reader_id),
            "book_id": str(book_id),
            "borrowed_date": TODAY.isoformat(),
            "due_date": (TODAY + timedelta(days=14)).isoformat(),
            "note": "Marked verification loan",
        },
        follow_redirects=True,
    )


def test_web_flows():
    app.config.update(TESTING=True)
    anonymous = app.test_client()
    for path in ("/", "/books", "/readers", "/loans"):
        response = anonymous.get(path)
        check(response.status_code == 302 and "/login" in response.location, f"{path} was not protected")
    rejected = anonymous.post("/books", data={"book_code": f"VERIFY-NO-CSRF-{SUFFIX}"})
    check(rejected.status_code == 400, "POST without CSRF token was not rejected")

    client = login_client()
    with connect_db() as conn:
        admin = conn.execute("SELECT password_hash FROM users WHERE username = %s", (ADMIN_USER,)).fetchone()
    check(admin and ADMIN_PASSWORD not in admin["password_hash"], "Admin password was not stored as a hash")
    check(admin["password_hash"].startswith(("scrypt:", "pbkdf2:")), "Unexpected password hash format")

    token = csrf_token(client, "/")
    response = client.post("/logout", data={"csrf_token": token}, follow_redirects=True)
    check(response.status_code == 200 and client.get("/").status_code == 302, "Logout did not clear the session")
    client = login_client()

    book_title = f"Marked verification book {SUFFIX}"
    book_id = create_book(client, BOOK_CODE, book_title, 1)
    result = client.get("/books?" + urlencode({"q": BOOK_CODE}))
    check(BOOK_CODE in result.get_data(as_text=True), "Book search did not find the new record")
    token = csrf_token(client, f"/books/{book_id}/edit")
    edited_title = f"Edited verification book {SUFFIX}"
    response = client.post(
        f"/books/{book_id}/edit",
        data={**book_form(BOOK_CODE, edited_title, 1), "csrf_token": token},
    )
    check(response.status_code == 302, "Book edit failed")
    check(edited_title in client.get("/books?" + urlencode({"q": edited_title})).get_data(as_text=True), "Edited book was not searchable")

    reader_name = f"Marked verification reader {SUFFIX}"
    reader_id = create_reader(client, READER_CODE, reader_name)
    result = client.get("/readers?" + urlencode({"q": READER_CODE}))
    check(READER_CODE in result.get_data(as_text=True), "Reader search did not find the new record")
    token = csrf_token(client, f"/readers/{reader_id}/edit")
    edited_reader = f"Edited verification reader {SUFFIX}"
    response = client.post(
        f"/readers/{reader_id}/edit",
        data={**reader_form(READER_CODE, edited_reader), "csrf_token": token},
    )
    check(response.status_code == 302, "Reader edit failed")
    check(edited_reader in client.get("/readers?" + urlencode({"q": edited_reader})).get_data(as_text=True), "Edited reader was not searchable")

    response = submit_loan(client, reader_id, book_id)
    check("\u0111\u00e3 ghi nh\u1eadn l\u01b0\u1ee3t m\u01b0\u1ee3n" in response.get_data(as_text=True).lower(), "Borrowing an available copy failed")
    response = submit_loan(client, reader_id, book_id)
    check("\u0111\u00e3 \u0111\u01b0\u1ee3c m\u01b0\u1ee3n h\u1ebft" in response.get_data(as_text=True).lower(), "Borrowing an exhausted title was not rejected")
    with connect_db() as conn:
        loan_id = conn.execute(
            "SELECT id FROM loans WHERE book_id = %s AND returned_date IS NULL", (book_id,)
        ).fetchone()["id"]

    token = csrf_token(client, f"/books/{book_id}/edit")
    response = client.post(
        f"/books/{book_id}/edit",
        data={**book_form(BOOK_CODE, edited_title, 0), "csrf_token": token},
    )
    check(response.status_code == 400, "Book quantity was allowed below active loans")
    with connect_db() as conn:
        quantity = conn.execute("SELECT total_quantity FROM books WHERE id = %s", (book_id,)).fetchone()["total_quantity"]
    check(quantity == 1, "Rejected quantity edit changed stored quantity")

    token = csrf_token(client, "/loans")
    response = client.post(f"/loans/{loan_id}/return", data={"csrf_token": token}, follow_redirects=True)
    check("\u0111\u00e3 ghi nh\u1eadn tr\u1ea3 s\u00e1ch" in response.get_data(as_text=True).lower(), "Returning the loan failed")
    token = csrf_token(client, "/loans")
    response = client.post(f"/loans/{loan_id}/return", data={"csrf_token": token}, follow_redirects=True)
    check("\u0111\u00e3 \u0111\u01b0\u1ee3c tr\u1ea3 tr\u01b0\u1edbc \u0111\u00f3" in response.get_data(as_text=True).lower(), "A second return was not rejected")

    token = csrf_token(client, "/books")
    response = client.post(f"/books/{book_id}/delete", data={"csrf_token": token}, follow_redirects=True)
    check("kh\u00f4ng th\u1ec3 x\u00f3a s\u00e1ch v\u00ec \u0111\u00e3 c\u00f3 l\u1ecbch s\u1eed m\u01b0\u1ee3n" in response.get_data(as_text=True).lower(), "Book history delete error was unclear")
    token = csrf_token(client, "/readers")
    response = client.post(f"/readers/{reader_id}/delete", data={"csrf_token": token}, follow_redirects=True)
    check("kh\u00f4ng th\u1ec3 x\u00f3a \u0111\u1ed9c gi\u1ea3 v\u00ec \u0111\u00e3 c\u00f3 l\u1ecbch s\u1eed m\u01b0\u1ee3n" in response.get_data(as_text=True).lower(), "Reader history delete error was unclear")
    with connect_db() as conn:
        check(conn.execute("SELECT 1 FROM books WHERE id = %s", (book_id,)).fetchone(), "Book with history was deleted")
        check(conn.execute("SELECT 1 FROM readers WHERE id = %s", (reader_id,)).fetchone(), "Reader with history was deleted")
    PASSED.append("login/logout, protected pages, CSRF, admin hash, CRUD/search, borrow/return, quantity and history constraints")

    concurrent_code = f"VERIFY-C-{SUFFIX}"
    concurrent_book_id = create_book(client, concurrent_code, f"Marked last-copy book {SUFFIX}", 1)
    barrier = threading.Barrier(2)

    def competing_borrow():
        borrower = login_client()
        token = csrf_token(borrower, "/loans")
        barrier.wait(timeout=15)
        response = borrower.post(
            "/loans",
            data={
                "csrf_token": token,
                "reader_id": str(reader_id),
                "book_id": str(concurrent_book_id),
                "borrowed_date": TODAY.isoformat(),
                "due_date": (TODAY + timedelta(days=14)).isoformat(),
                "note": "Concurrent last-copy verification",
            },
            follow_redirects=True,
        )
        return response.get_data(as_text=True).lower()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: competing_borrow(), range(2)))
    with connect_db() as conn:
        active_count = conn.execute(
            "SELECT COUNT(*) AS count FROM loans WHERE book_id = %s AND returned_date IS NULL",
            (concurrent_book_id,),
        ).fetchone()["count"]
    check(active_count == 1, f"Concurrent last-copy borrowing created {active_count} active loans")
    check(sum("\u0111\u00e3 ghi nh\u1eadn l\u01b0\u1ee3t m\u01b0\u1ee3n" in body for body in results) == 1, "Concurrent requests did not yield exactly one success")
    check(sum("\u0111\u00e3 \u0111\u01b0\u1ee3c m\u01b0\u1ee3n h\u1ebft" in body for body in results) == 1, "Concurrent losing request did not report exhausted stock")
    PASSED.append("two concurrent requests for the last copy: exactly one loan committed")


def test_runtime_role():
    with connect_db() as conn:
        role = conn.execute(
            """
            SELECT r.rolsuper, r.rolcreatedb, r.rolcreaterole,
                   has_database_privilege(current_user, current_database(), 'CREATE') AS can_create_in_database,
                   has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_in_schema,
                   has_table_privilege(current_user, 'public.books', 'TRUNCATE') AS can_truncate,
                   has_table_privilege(current_user, 'public.books', 'SELECT') AS can_select,
                   has_table_privilege(current_user, 'public.books', 'INSERT') AS can_insert,
                   has_table_privilege(current_user, 'public.books', 'UPDATE') AS can_update,
                   has_table_privilege(current_user, 'public.books', 'DELETE') AS can_delete,
                   has_sequence_privilege(current_user, pg_get_serial_sequence('public.users', 'id'), 'USAGE') AS can_use_user_id_sequence
            FROM pg_roles AS r WHERE r.rolname = current_user
            """
        ).fetchone()
    check(role is not None, "Application DB role was not found")
    check(not role["rolsuper"] and not role["rolcreatedb"] and not role["rolcreaterole"], "Application role has an elevated role attribute")
    check(not role["can_create_in_database"] and not role["can_create_in_schema"] and not role["can_truncate"], "Application role has unintended DDL/TRUNCATE privileges")
    check(all(role[key] for key in ("can_select", "can_insert", "can_update", "can_delete", "can_use_user_id_sequence")), "Application role is missing CRUD or identity sequence access")
    PASSED.append("application DB role: CRUD and sequence access; no superuser, database/role creation, DDL or TRUNCATE")


def test_nginx_proxy():
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    base = "http://nginx"
    login_page = opener.open(base + "/login", timeout=10)
    content = login_page.read()
    match = re.search(rb'name="csrf_token" value="([^"]+)"', content)
    check(match is not None, "Nginx login page did not contain a CSRF token")
    headers = login_page.headers
    for header, expected in (
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ):
        check(headers.get(header) == expected, f"Nginx header {header} was missing or incorrect")

    css = opener.open(base + "/static/styles.css", timeout=10)
    check(css.status == 200 and "text/css" in css.headers.get("Content-Type", ""), "CSS did not load through Nginx")

    body = urlencode({"csrf_token": match.group(1).decode(), "username": ADMIN_USER, "password": ADMIN_PASSWORD}).encode()
    response = opener.open(Request(base + "/login", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10)
    check(response.status == 200 and response.geturl().rstrip("/") == base, "Login through Nginx failed")

    try:
        opener.open(Request(base + "/logout", data=b"", headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10)
        raise AssertionError("Nginx POST without CSRF token was accepted")
    except HTTPError as error:
        check(error.code == 400, f"Nginx CSRF rejection returned {error.code}")
        error.read()

    books = opener.open(base + "/books", timeout=10)
    match = re.search(rb'name="csrf_token" value="([^"]+)"', books.read())
    check(match is not None, "Authenticated books page did not contain a CSRF token")
    body = urlencode({"csrf_token": match.group(1).decode()}).encode()
    logged_out = opener.open(Request(base + "/logout", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10)
    check("/login" in logged_out.geturl(), "CSRF-protected logout through Nginx failed")
    protected = opener.open(base + "/readers", timeout=10)
    check("/login" in protected.geturl(), "Nginx request after logout was not redirected to login")
    PASSED.append("Nginx headers, CSS, login/logout, protected route and CSRF rejection/acceptance through proxy")


if __name__ == "__main__":
    test_runtime_role()
    test_web_flows()
    test_nginx_proxy()
    for item in PASSED:
        print(f"PASS: {item}")
    print(f"Marked test data prefix: VERIFY-{SUFFIX}")
