import base64
import json
import os
import secrets
import sqlite3
import time
from hashlib import sha256

from cryptography.fernet import Fernet
from oauth2client.client import OAuth2Credentials
from pydrive2.auth import GoogleAuth

from .drive_service import build_google_auth_settings, get_authenticated_drive

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "gdam_session")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 24 * 14)))


def require_login():
    return os.getenv("REQUIRE_LOGIN", "0") == "1"


def get_auth_database_url():
    return os.getenv("DATABASE_URL", "").strip()


def get_auth_db_path():
    path = os.getenv("AUTH_DB_PATH")
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        return path
    app_data = os.path.abspath(".app_data")
    os.makedirs(app_data, exist_ok=True)
    return os.path.join(app_data, "gdam_auth.db")


def get_public_app_url(request=None):
    configured = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
    if configured:
        return configured
    if request:
        return str(request.base_url).rstrip("/")
    return "http://127.0.0.1:8000"


def get_frontend_url():
    return os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").strip().rstrip("/")


def get_cookie_secure():
    value = os.getenv("SESSION_COOKIE_SECURE")
    if value is not None:
        return value == "1"
    return get_public_app_url().startswith("https://")


def get_cookie_samesite():
    configured = os.getenv("SESSION_COOKIE_SAMESITE", "").strip().lower()
    if configured in {"lax", "strict", "none"}:
        return configured
    return "none" if get_cookie_secure() else "lax"


def get_fernet():
    secret = os.getenv("TOKEN_ENCRYPTION_SECRET") or os.getenv("APP_SECRET_KEY")
    if not secret:
        if require_login():
            raise RuntimeError("Set TOKEN_ENCRYPTION_SECRET before enabling REQUIRE_LOGIN.")
        secret = "local-development-only-change-me"
    key = base64.urlsafe_b64encode(sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


class AuthDbConnection:
    def __init__(self):
        self.kind = "postgres" if get_auth_database_url() else "sqlite"
        self.connection = None

    def __enter__(self):
        if self.kind == "postgres":
            if psycopg is None:
                raise RuntimeError("psycopg is required when DATABASE_URL is set.")
            self.connection = psycopg.connect(get_auth_database_url(), row_factory=dict_row)
        else:
            self.connection = sqlite3.connect(get_auth_db_path())
            self.connection.row_factory = sqlite3.Row
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.connection:
            return
        if exc_type:
            self.connection.rollback()
        else:
            self.connection.commit()
        self.connection.close()

    def sql(self, query):
        return query.replace("?", "%s") if self.kind == "postgres" else query

    def execute(self, query, params=()):
        return self.connection.execute(self.sql(query), params)


def connect_auth_db():
    return AuthDbConnection()


def init_auth_db():
    with connect_auth_db() as db:
        db.execute(
            """
            create table if not exists users (
                id text primary key,
                email text unique not null,
                name text not null default '',
                picture text not null default '',
                credentials text not null,
                created_at integer not null,
                updated_at integer not null
            )
            """
        )
        db.execute(
            """
            create table if not exists sessions (
                id text primary key,
                user_id text not null,
                created_at integer not null,
                expires_at integer not null,
                foreign key(user_id) references users(id)
            )
            """
        )
        db.execute("create index if not exists idx_sessions_expires_at on sessions(expires_at)")
        db.execute(
            """
            create table if not exists signature_tokens (
                token text primary key,
                user_id text not null,
                created_at integer not null,
                foreign key(user_id) references users(id)
            )
            """
        )


def encrypt_text(value):
    return get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value):
    return get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def create_google_auth_for_web(redirect_uri):
    gauth = GoogleAuth(settings=build_google_auth_settings())
    gauth.LoadClientConfig()
    gauth.client_config["redirect_uri"] = redirect_uri
    return gauth


def build_google_login_url(request, state):
    redirect_uri = "{}/auth/google/callback".format(get_public_app_url(request))
    gauth = create_google_auth_for_web(redirect_uri)
    url = gauth.GetAuthUrl()
    separator = "&" if "?" in url else "?"
    return "{}{}state={}&prompt=consent".format(url, separator, state)


def exchange_google_code(request, code):
    redirect_uri = "{}/auth/google/callback".format(get_public_app_url(request))
    gauth = create_google_auth_for_web(redirect_uri)
    gauth.Auth(code)
    return gauth.credentials


def get_user_info(credentials):
    import httplib2

    http = credentials.authorize(httplib2.Http())
    response, content = http.request("https://www.googleapis.com/oauth2/v2/userinfo")
    if int(response.status) >= 400:
        raise RuntimeError("Could not fetch Google user profile.")
    return json.loads(content.decode("utf-8"))


def save_user_from_credentials(credentials):
    profile = get_user_info(credentials)
    email = (profile.get("email") or "").strip().lower()
    if not email:
        raise RuntimeError("Google did not return an email address.")
    now = int(time.time())
    encrypted_credentials = encrypt_text(credentials.to_json())

    with connect_auth_db() as db:
        existing = db.execute("select id from users where email = ?", (email,)).fetchone()
        user_id = existing["id"] if existing else secrets.token_urlsafe(18)
        if existing:
            db.execute(
                """
                update users
                set name = ?, picture = ?, credentials = ?, updated_at = ?
                where id = ?
                """,
                (profile.get("name", ""), profile.get("picture", ""), encrypted_credentials, now, user_id),
            )
        else:
            db.execute(
                """
                insert into users (id, email, name, picture, credentials, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, email, profile.get("name", ""), profile.get("picture", ""), encrypted_credentials, now, now),
            )
    return get_user(user_id)


def create_session(user_id):
    now = int(time.time())
    session_id = secrets.token_urlsafe(32)
    with connect_auth_db() as db:
        db.execute(
            "insert into sessions (id, user_id, created_at, expires_at) values (?, ?, ?, ?)",
            (session_id, user_id, now, now + SESSION_TTL_SECONDS),
        )
    return session_id


def delete_session(session_id):
    if not session_id:
        return
    with connect_auth_db() as db:
        db.execute("delete from sessions where id = ?", (session_id,))


def get_user(user_id):
    with connect_auth_db() as db:
        row = db.execute(
            "select id, email, name, picture, created_at, updated_at from users where id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def get_session_user(session_id):
    if not session_id:
        return None
    now = int(time.time())
    with connect_auth_db() as db:
        row = db.execute(
            """
            select users.id, users.email, users.name, users.picture, users.created_at, users.updated_at
            from sessions
            join users on users.id = sessions.user_id
            where sessions.id = ? and sessions.expires_at > ?
            """,
            (session_id, now),
        ).fetchone()
    return dict(row) if row else None


def get_credentials_for_user(user_id):
    with connect_auth_db() as db:
        row = db.execute("select credentials from users where id = ?", (user_id,)).fetchone()
    if not row:
        raise RuntimeError("User was not found.")
    return OAuth2Credentials.from_json(decrypt_text(row["credentials"]))


def save_credentials_for_user(user_id, credentials):
    with connect_auth_db() as db:
        db.execute(
            "update users set credentials = ?, updated_at = ? where id = ?",
            (encrypt_text(credentials.to_json()), int(time.time()), user_id),
        )


def get_drive_for_user(user_id):
    credentials = get_credentials_for_user(user_id)
    return get_authenticated_drive(
        credentials=credentials,
        on_credentials_updated=lambda updated_credentials: save_credentials_for_user(user_id, updated_credentials),
    )


def save_signature_token_owner(token, user_id):
    if not token or not user_id:
        return
    with connect_auth_db() as db:
        if db.kind == "postgres":
            db.execute(
                """
                insert into signature_tokens (token, user_id, created_at)
                values (?, ?, ?)
                on conflict (token) do update set user_id = excluded.user_id, created_at = excluded.created_at
                """,
                (token, user_id, int(time.time())),
            )
        else:
            db.execute(
                "insert or replace into signature_tokens (token, user_id, created_at) values (?, ?, ?)",
                (token, user_id, int(time.time())),
            )


def get_drive_for_signature_token(token):
    with connect_auth_db() as db:
        row = db.execute("select user_id from signature_tokens where token = ?", (token,)).fetchone()
    if not row:
        if require_login():
            raise RuntimeError("Signature link was not found.")
        return get_authenticated_drive()
    return get_drive_for_user(row["user_id"])
