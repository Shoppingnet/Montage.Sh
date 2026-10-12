"""حسابات الموظفين: تسجيل الدخول، الأدوار (admin / staff / viewer)، وجلسة بكوكي موقّع (30 يوم)."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import HTTPException, Request

BASE = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR", BASE / "data"))
DB = DATA / "users.db"
COOKIE = "mtg_session"
SESSION_DAYS = 30
ROLES = {"admin": "مدير", "staff": "موظف", "viewer": "مشاهد"}


def _secret():
    """مفتاح التوقيع ديال الكوكي: من .env، ولا كيتصاوب مرة وحدة ويتحفظ فـ data/."""
    s = os.getenv("SESSION_SECRET")
    if s:
        return s.encode()
    f = DATA / ".session_secret"
    if not f.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, name TEXT, role TEXT, pw_hash TEXT,
            active INTEGER DEFAULT 1, created REAL, last_login REAL)""")
        # أول مرة: المدير من APP_USER / APP_PASSWORD ديال .env
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            u, p = os.getenv("APP_USER", "admin"), os.getenv("APP_PASSWORD", "change-me")
            c.execute("INSERT INTO users(username,name,role,pw_hash,created) VALUES(?,?,?,?,?)",
                      (u, "المدير", "admin", hash_pw(p), time.time()))


def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${h}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex(), h)


def get_user(username=None, uid=None):
    with db() as c:
        if uid is not None:
            r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        else:
            r = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(r) if r else None


def list_users():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY role, name")]


def create_user(username, name, role, pw):
    username = username.strip().lower()
    if not username or len(pw) < 4 or role not in ROLES:
        raise HTTPException(400, "خاص سمية الدخول، باسورد (4 حروف على الأقل)، ودور صحيح")
    with db() as c:
        if c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(400, "هاد السمية ديجا كاينة")
        c.execute("INSERT INTO users(username,name,role,pw_hash,created) VALUES(?,?,?,?,?)",
                  (username, name.strip() or username, role, hash_pw(pw), time.time()))


def update_user(uid, **f):
    if "pw" in f:
        f["pw_hash"] = hash_pw(f.pop("pw"))
    if not f:
        return
    sets = ",".join(f"{k}=?" for k in f)
    with db() as c:
        c.execute(f"UPDATE users SET {sets} WHERE id=?", (*f.values(), uid))


def login(username, pw):
    u = get_user(username=username.strip().lower())
    if not u or not u["active"] or not check_pw(pw, u["pw_hash"]):
        return None
    update_user(u["id"], last_login=time.time())
    return u


# ───────────────────────── الكوكي الموقّع ─────────────────────────
def make_token(uid):
    payload = base64.urlsafe_b64encode(json.dumps({"u": uid, "t": int(time.time())}).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def read_token(token):
    try:
        payload, sig = token.split(".", 1)
        if not hmac.compare_digest(hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32], sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if time.time() - data["t"] > SESSION_DAYS * 86400:
            return None
        return data["u"]
    except (ValueError, KeyError, TypeError):
        return None


def user_from_request(request: Request):
    """المستعمل من الكوكي (ولا None)."""
    uid = read_token(request.cookies.get(COOKIE, ""))
    u = get_user(uid=uid) if uid is not None else None
    return u if u and u["active"] else None


def current_user(request: Request):
    """Dependency: المستعمل الحالي (الـ middleware ديجا تأكد منو)."""
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "خاصك تدخل")
    return u


def require_role(*roles):
    def dep(request: Request):
        u = current_user(request)
        if u["role"] not in roles:
            raise HTTPException(403, "ماعندكش الصلاحية لهاد العملية")
        return u
    return dep


def can_manage(user, owner):
    """المدير كيقدر على كولشي؛ الموظف غير على ديالو؛ المشاهد لا."""
    return user["role"] == "admin" or (user["role"] == "staff" and (not owner or owner == user["username"]))
