"""صفحات الهبوط: صفحة عمومية لكل منتوج (بلا باسورد)، والطلبات كيمشيو للـ CRM."""
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import requests
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR", BASE / "data"))
DB = DATA / "landing.db"
PAGES = DATA / "pages"
PAGES.mkdir(parents=True, exist_ok=True)
T = Jinja2Templates(directory=str(BASE / "templates"))
_LOCK = threading.Lock()

# الـ CRM ديال Shopping Net: POST /storeApi/ (name, tel, adress, city, quantity, price, source, ProductReference)
CRM_URL = os.getenv("CRM_URL", "").rstrip("/")
CRM_SECRET = os.getenv("CRM_SECRET", "")


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pages(
            slug TEXT PRIMARY KEY, name TEXT, product_ref TEXT, price TEXT, angle TEXT, product_info TEXT,
            job_id TEXT, content TEXT, images TEXT, video TEXT DEFAULT '', published INTEGER DEFAULT 1,
            views INTEGER DEFAULT 0, created REAL, updated REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS leads(
            id TEXT PRIMARY KEY, slug TEXT, name TEXT, tel TEXT, city TEXT, adress TEXT, quantity INTEGER,
            price TEXT, crm_status TEXT, crm_error TEXT, created REAL)""")
        try:
            c.execute("ALTER TABLE pages ADD COLUMN owner TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass


def slugify(s):
    s = re.sub(r"[^\w؀-ۿ-]+", "-", s.strip().lower()).strip("-")
    return s[:60] or uuid.uuid4().hex[:8]


def get_page(slug):
    with db() as c:
        r = c.execute("SELECT * FROM pages WHERE slug=?", (slug,)).fetchone()
    if not r:
        return None
    p = dict(r)
    p["content"] = json.loads(p["content"] or "{}")
    p["images"] = json.loads(p["images"] or "[]")
    return p


def list_pages():
    with db() as c:
        rows = c.execute("SELECT p.*, (SELECT COUNT(*) FROM leads l WHERE l.slug=p.slug) leads "
                         "FROM pages p ORDER BY created DESC").fetchall()
    return [dict(r) for r in rows]


def save_page(slug, **fields):
    for k in ("content", "images"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k], ensure_ascii=False)
    fields["updated"] = time.time()
    with db() as c:
        if c.execute("SELECT 1 FROM pages WHERE slug=?", (slug,)).fetchone():
            sets = ",".join(f"{k}=?" for k in fields)
            c.execute(f"UPDATE pages SET {sets} WHERE slug=?", (*fields.values(), slug))
        else:
            fields["created"] = time.time()
            cols = ",".join(["slug", *fields])
            c.execute(f"INSERT INTO pages({cols}) VALUES({','.join('?' * (len(fields) + 1))})", (slug, *fields.values()))


def delete_page(slug):
    with db() as c:
        c.execute("DELETE FROM pages WHERE slug=?", (slug,))


def send_to_crm(lead, page):
    """كيصيفط الطلب للـ CRM. كيرجع (ok, error)."""
    if not CRM_URL:
        return False, "CRM_URL ماكايناش فـ .env"
    data = {"name": lead["name"], "tel": lead["tel"], "adress": lead.get("adress") or "", "city": lead["city"],
            "quantity": lead.get("quantity") or 1, "price": lead.get("price") or page.get("price") or "",
            "source": "landing:" + page["slug"], "ProductReference": page.get("product_ref") or page["name"]}
    if CRM_SECRET:
        data["secret"] = CRM_SECRET
    try:
        r = requests.post(f"{CRM_URL}/storeApi/", data=data, timeout=15)
        if r.status_code >= 400:
            return False, f"CRM {r.status_code}: {r.text[:200]}"
        return True, ""
    except requests.RequestException as e:
        return False, str(e)[:200]


def retry_failed_leads():
    """الطلبات اللي ماوصلوش للـ CRM (الشبكة طاحت...) كنعاودو نصيفطوهم."""
    with db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM leads WHERE crm_status='failed' ORDER BY created LIMIT 20")]
    for lead in rows:
        page = get_page(lead["slug"])
        if not page:
            continue
        ok, err = send_to_crm(lead, page)
        with db() as c:
            c.execute("UPDATE leads SET crm_status=?, crm_error=? WHERE id=?", ("sent" if ok else "failed", err, lead["id"]))


# ───────────────────────── الصفحات العمومية (بلا باسورد) ─────────────────────────
public = FastAPI()


@public.get("/{slug}", response_class=HTMLResponse)
def landing_page(request: Request, slug: str):
    p = get_page(slug)
    if not p or not p["published"]:
        raise HTTPException(404, "الصفحة ماكايناش")
    with db() as c:
        c.execute("UPDATE pages SET views=views+1 WHERE slug=?", (slug,))
    ai = [im for im in p["images"] if im.startswith("ai_")]
    others = [im for im in p["images"] if not im.startswith("ai_")]
    return T.TemplateResponse(request, "landing.html", {"p": p, "ai": ai, "others": others,
                                                        "sent": request.query_params.get("ok")})


@public.get("/{slug}/media/{name}")
def landing_media(slug: str, name: str):
    f = PAGES / Path(slug).name / Path(name).name
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, headers={"Cache-Control": "public, max-age=86400"})


@public.post("/{slug}/order")
def landing_order(slug: str, name: str = Form(...), tel: str = Form(...), city: str = Form(...),
                  adress: str = Form(""), quantity: int = Form(1), website: str = Form("")):
    p = get_page(slug)
    if not p:
        raise HTTPException(404)
    if website:  # honeypot: الروبوتات كيعمروه
        return RedirectResponse(f"/p/{slug}?ok=1", status_code=303)
    tel_clean = re.sub(r"\D", "", tel)
    if len(tel_clean) < 9 or len(name.strip()) < 2:
        return RedirectResponse(f"/p/{slug}?err=1#order", status_code=303)
    lead = {"id": uuid.uuid4().hex[:12], "slug": slug, "name": name.strip()[:80], "tel": tel_clean[:15],
            "city": city.strip()[:60], "adress": adress.strip()[:200], "quantity": max(1, min(quantity, 20)),
            "price": p.get("price") or "", "created": time.time()}
    # نفس التيليفون فأقل من دقيقة = دوبل كليك، ماكنعاودوش
    with _LOCK, db() as c:
        dup = c.execute("SELECT 1 FROM leads WHERE slug=? AND tel=? AND created>?",
                        (slug, lead["tel"], time.time() - 60)).fetchone()
        if not dup:
            c.execute("INSERT INTO leads(id,slug,name,tel,city,adress,quantity,price,crm_status,created) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?)", (*[lead[k] for k in ("id", "slug", "name", "tel", "city", "adress",
                                                                          "quantity", "price")], "pending", lead["created"]))
    if not dup:
        ok, err = send_to_crm(lead, p)
        with db() as c:
            c.execute("UPDATE leads SET crm_status=?, crm_error=? WHERE id=?", ("sent" if ok else "failed", err, lead["id"]))
    return RedirectResponse(f"/p/{slug}?ok=1", status_code=303)
