"""نظام الدبلجة بالدارجة — واجهة الويب + الخدامة اللي كيعالجو الفيديوهات فالخلفية."""
import json
import os
import secrets
import shutil
import sqlite3
import threading
import time
import traceback
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse  # noqa: E402
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

import ad_images  # noqa: E402
import pipeline as P  # noqa: E402

BASE = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR", BASE / "data"))
JOBS = DATA / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)
DB = DATA / "jobs.db"
LOCK = threading.Lock()

STATUS_AR = {
    "queued": "فالانتظار", "analyzing": "كيتحلل", "review": "خاصو مراجعة", "edit_queued": "أمر فالانتظار",
    "editing": "كيطبق الأمر", "approved": "مقبول — فالانتظار", "rendering": "كيتصاوب الصوت والمونتاج",
    "done": "واجد ✓", "error": "غلطة",
}


def voices():
    raw = os.getenv("VOICES", "MASTER ADS VOICE=4GrPPhyFD4Md4Rvs3kqR")
    out = []
    for item in raw.split(";"):
        if "=" in item:
            n, v = item.split("=", 1)
            out.append((n.strip(), v.strip()))
    return out


# ───────────────────────── قاعدة البيانات ─────────────────────────
def db():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS jobs(
            id TEXT PRIMARY KEY, batch TEXT, name TEXT, source TEXT, product_info TEXT, instruction TEXT,
            voice TEXT, auto_approve INTEGER, make_images INTEGER, status TEXT, step TEXT, error TEXT,
            blur REAL, enhanced TEXT, plan TEXT, plan_prev TEXT, pending TEXT,
            img_status TEXT DEFAULT '', img_error TEXT, created REAL, updated REAL)""")
        try:
            c.execute("ALTER TABLE jobs ADD COLUMN opts TEXT DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE jobs ADD COLUMN tries INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        # فيديو كان كيتصاوب ملي طفات الخدمة: كنعاودوه، ولكن إلا وقع هادشي جوج مرات = هو اللي كيطيّح السيرفر، نوقفوه
        c.execute("UPDATE jobs SET tries=COALESCE(tries,0)+1 WHERE status IN ('analyzing','editing','rendering')")
        c.execute("UPDATE jobs SET status='error', step='', error='هاد الفيديو طيّح الخدمة جوج مرات (غالبا طويل بزاف"
                  " على هاد السيرفر). قصّو ولا جرب فيديو أقصر.' WHERE status IN ('analyzing','editing','rendering')"
                  " AND tries>=2")
        # إلا طفا السيرفر وسط الخدمة، نرجعو الخدمات للانتظار
        c.execute("UPDATE jobs SET status='queued' WHERE status='analyzing'")
        c.execute("UPDATE jobs SET status='edit_queued' WHERE status='editing'")
        c.execute("UPDATE jobs SET status='approved' WHERE status='rendering'")
        c.execute("UPDATE jobs SET img_status='queued' WHERE img_status='working'")


MUSIC = DATA / "music"
MUSIC.mkdir(parents=True, exist_ok=True)
MUSIC_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg"}
# الاختيارات ديال كل فيديو: ترجمة مكتوبة، موسيقى (none / random / سمية الملف)، مقاسات، نسخ A/B
DEFAULT_OPTS = {"subs": 1, "music": "none", "sizes": 0, "ab": 0}


def music_files():
    return sorted(p.name for p in MUSIC.iterdir() if p.suffix.lower() in MUSIC_EXT)


def pick_music(choice):
    files = music_files()
    if choice == "random" and files:
        import random
        return MUSIC / random.choice(files)
    if choice in files:
        return MUSIC / choice
    return None


def opts_from_form(form):
    return {"subs": 1 if form.get("opt_subs") else 0, "music": form.get("opt_music") or "none",
            "sizes": 1 if form.get("opt_sizes") else 0, "ab": 1 if form.get("opt_ab") else 0}


def get(job_id):
    with db() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        raise HTTPException(404, "ماكايناش")
    j = dict(r)
    j["plan"] = json.loads(j["plan"]) if j["plan"] else None
    j["opts"] = {**DEFAULT_OPTS, **json.loads(j.get("opts") or "{}")}
    return j


def update(job_id, **kw):
    kw["updated"] = time.time()
    for k in ("plan", "plan_prev"):
        if k in kw and isinstance(kw[k], dict):
            kw[k] = json.dumps(kw[k], ensure_ascii=False)
    sets = ",".join(f"{k}=?" for k in kw)
    with db() as c:
        c.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*kw.values(), job_id))


def claim(from_status, to_status, col="status"):
    with LOCK, db() as c:
        r = c.execute(f"SELECT id FROM jobs WHERE {col}=? ORDER BY created LIMIT 1", (from_status,)).fetchone()
        if not r:
            return None
        c.execute(f"UPDATE jobs SET {col}=?, updated=? WHERE id=?", (to_status, time.time(), r["id"]))
        return r["id"]


def jdir(job_id):
    d = JOBS / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_photo(data: bytes, out: Path):
    """كيسجل تصويرة المنتوج JPG (مدوّرة صحيحة وماشي كبيرة بزاف)."""
    from io import BytesIO
    from PIL import Image, ImageOps
    try:
        img = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
    except Exception:
        raise HTTPException(400, "هادي ماشي تصويرة (JPG ولا PNG ولا WEBP)")
    img.thumbnail((2000, 2000))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)


def product_photo(job_id):
    """تصويرة المنتوج ديال هاد الفيديو، ولا ديال الدفعة كاملة."""
    p = JOBS / job_id / "product.jpg"
    if p.exists():
        return p
    j = get(job_id)
    b = DATA / "uploads" / (j["batch"] if j else "") / "product.jpg"
    return b if j and b.exists() else None


def work_video(job_id):
    d = jdir(job_id)
    for name in ("enhanced.mp4",):
        if (d / name).exists():
            return d / name
    src = sorted(d.glob("source.*"))
    if not src:
        raise RuntimeError("الفيديو ماكاينش")
    return src[0]


# ───────────────────────── الخدامة فالخلفية ─────────────────────────
def stage_analyze(job_id):
    j = get(job_id)
    d = jdir(job_id)
    update(job_id, step="كيتحمّل")
    if not list(d.glob("source.*")):
        P.download(j["source"], d)
    src = sorted(d.glob("source.*"))[0]
    update(job_id, step="كيفحص الوضوح")
    score, need = P.needs_enhance(src)
    enhanced = ""
    if need and os.getenv("AUTO_ENHANCE", "1") == "1":
        update(job_id, step="كيوضح الفيديو", blur=score)
        enhanced = P.enhance(src, d / "enhanced.mp4")
    update(job_id, step="Gemini كيشوف الفيديو وكيكتب السكريبت", blur=score, enhanced=enhanced)
    plan = P.analyze(work_video(job_id), j["product_info"], j["instruction"], product_photo(job_id))
    update(job_id, plan=plan, step="", error="",
           status="approved" if j["auto_approve"] else "review",
           img_status="queued" if j["make_images"] else j["img_status"])


def stage_edit(job_id):
    j = get(job_id)
    plan = P.apply_instruction(j["plan"], j["pending"], P.duration(work_video(job_id)), j["product_info"])
    update(job_id, plan_prev=j["plan"], plan=plan, pending="", step="", error="",
           status="approved" if j["auto_approve"] else "review")


def stage_render(job_id):
    j = get(job_id)
    d = jdir(job_id)
    plan, o = j["plan"], j["opts"]
    work = d / "voice"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    for old in d.glob("final*.mp4"):
        old.unlink()
    music = pick_music(o["music"])
    update(job_id, step="كيصاوب التعليق والمونتاج")
    placed, total = P.render_final(work_video(job_id), plan, j["voice"], work, d / "final.mp4",
                                   subs=bool(o["subs"]), music=music)
    P.write_srt(placed, d / "final.srt")
    if o["ab"] and plan.get("hooks") and plan["segments"]:
        for k, hook in zip("bc", plan["hooks"]):
            update(job_id, step=f"كيصاوب النسخة {k.upper()} (hook آخر)")
            alt = json.loads(json.dumps(plan))
            alt["segments"][0]["text"] = hook
            P.render_final(work_video(job_id), alt, j["voice"], work, d / f"final_{k}.mp4",
                           subs=bool(o["subs"]), music=music)
    if o["sizes"]:
        update(job_id, step="كيصاوب المقاسات الأخرى")
        P.make_sizes(d / "final.mp4", d)
    update(job_id, status="done", step="", error="")


def stage_images(job_id):
    j = get(job_id)
    out = jdir(job_id) / "ads"
    shutil.rmtree(out, ignore_errors=True)
    ad_images.make_ad_images(work_video(job_id), j["plan"]["ad"], out, j["plan"].get("product", ""),
                             j["plan"].get("frames"), product_photo(job_id))
    update(job_id, img_status="done", img_error="")


def _child(fn_name, jid, conn):
    try:
        os.nice(10)  # الخدمة التقيلة بأولوية ضعيفة، باش الصفحة تبقا سريعة
        globals()[fn_name](jid)
        conn.send(None)
    except Exception as e:  # noqa
        traceback.print_exc()
        conn.send(str(e) or type(e).__name__)


def run_isolated(fn, jid):
    """كل خدمة كتخدم فبرنامج بوحدها: ملي كتسالي الذاكرة كترجع كاملة، والسيت مايتبلوكاش."""
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    p = ctx.Process(target=_child, args=(fn.__name__, jid, child), daemon=True)
    p.start()
    child.close()
    p.join()
    err = parent.recv() if parent.poll() else "الخدمة توقفات (غالبا ماكفاتهاش الذاكرة RAM)"
    if err:
        raise RuntimeError(err)


def worker(n):
    while True:
        did = False
        for frm, to, fn, col in (("approved", "rendering", stage_render, "status"),
                                 ("edit_queued", "editing", stage_edit, "status"),
                                 ("queued", "analyzing", stage_analyze, "status"),
                                 ("queued", "working", stage_images, "img_status")):
            jid = claim(frm, to, col)
            if not jid:
                continue
            did = True
            try:
                run_isolated(fn, jid)
            except Exception as e:  # noqa
                traceback.print_exc()
                if col == "img_status":
                    update(jid, img_status="error", img_error=str(e)[:500])
                else:
                    update(jid, status="error", step="", error=str(e)[:800])
            break
        if not did:
            time.sleep(2)


# ───────────────────────── الويب ─────────────────────────
security = HTTPBasic()


def auth(cred: HTTPBasicCredentials = Depends(security)):
    # bytes باش مايطيحش ملي تكون كلمة السر فيها حروف عربية
    ok_u = secrets.compare_digest(cred.username.encode(), os.getenv("APP_USER", "admin").encode())
    ok_p = secrets.compare_digest(cred.password.encode(), os.getenv("APP_PASSWORD", "change-me").encode())
    if not (ok_u and ok_p):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})


app = FastAPI(dependencies=[Depends(auth)])
T = Jinja2Templates(directory=str(BASE / "templates"))
T.env.globals.update(STATUS_AR=STATUS_AR, PLACEMENTS=ad_images.PLACEMENTS)


@app.on_event("startup")
def _start():
    init_db()
    for i in range(int(os.getenv("WORKERS", "2"))):
        threading.Thread(target=worker, args=(i,), daemon=True).start()


def list_jobs(batch=None, status=None):
    q, args = "SELECT * FROM jobs WHERE 1=1", []
    if batch:
        q += " AND batch=?"
        args.append(batch)
    if status:
        q += " AND status=?"
        args.append(status)
    with db() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY created DESC LIMIT 300", args)]


def disk_info():
    """البلاصة الخاوية فالديسك (مشترك مع برامج أخرى فالسيرفر)."""
    try:
        u = shutil.disk_usage(DATA)
    except OSError:
        return None
    jobs_bytes = sum(f.stat().st_size for f in JOBS.rglob("*") if f.is_file()) if JOBS.exists() else 0
    return {"free_gb": round(u.free / 1e9, 1), "pct": round(100 * u.used / u.total),
            "jobs_gb": round(jobs_bytes / 1e9, 2), "low": u.free < float(os.getenv("DISK_WARN_GB", "5")) * 1e9}


@app.get("/")
def index(request: Request, batch: str = "", status: str = ""):
    with db() as c:
        counts = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
        batches = [dict(r) for r in c.execute(
            "SELECT batch, MIN(created) t, COUNT(*) n, SUM(status='done') done, SUM(status='review') rev "
            "FROM jobs GROUP BY batch ORDER BY t DESC LIMIT 15")]
    return T.TemplateResponse(request, "index.html", {
        "jobs": list_jobs(batch or None, status or None), "voices": voices(), "counts": counts,
        "batches": batches, "batch": batch, "status": status, "disk": disk_info(), "music": music_files()})


@app.post("/submit")
async def submit(links_text: str = Form(""), product_info: str = Form(""), instruction: str = Form(""),
                 voice: str = Form(""), auto_approve: str = Form(""), make_images: str = Form(""),
                 links_file: UploadFile | None = File(None), videos: list[UploadFile] = File(default=[]),
                 product_photo_file: UploadFile | None = File(None), opt_subs: str = Form(""),
                 opt_music: str = Form("none"), opt_sizes: str = Form(""), opt_ab: str = Form(""),
                 merge: str = Form("")):
    batch = time.strftime("%m%d-%H%M") + "-" + uuid.uuid4().hex[:4]
    up = DATA / "uploads" / batch
    up.mkdir(parents=True, exist_ok=True)
    items, errors = [], []  # (name, source)
    if product_photo_file and product_photo_file.filename:
        save_photo(await product_photo_file.read(), up / "product.jpg")

    links = P.URL_RE.findall(links_text or "")
    if links_file and links_file.filename:
        p = up / Path(links_file.filename).name
        p.write_bytes(await links_file.read())
        if p.suffix.lower() in P.VIDEO_EXT:
            items.append((p.name, f"local:{p}"))
        else:
            links += P.extract_links(p)
    for v in videos or []:
        if v and v.filename:
            p = up / Path(v.filename).name
            with open(p, "wb") as f:
                shutil.copyfileobj(v.file, f)
            items.append((p.name, f"local:{p}"))
    for url in dict.fromkeys(links):
        kind, val = P.classify_link(url)
        try:
            if kind == "folder":
                for fid, name in P.list_drive_folder(val):
                    items.append((name, f"drive:{fid}"))
            elif kind == "file":
                items.append((val[:10], f"drive:{val}"))
            else:
                items.append((Path(url.split("?")[0]).name or url[:30], f"url:{url}"))
        except Exception as e:  # noqa
            errors.append(f"{url}: {e}")
    if not items:
        raise HTTPException(400, "ماكاين حتى فيديو. " + " | ".join(errors))
    if merge and len(items) > 1:
        # المونتاج: كنجمعو الفيديوهات كاملين ففيديو واحد (خاصهم يكونو محليين)
        paths = []
        for name, src in items:
            kind, _, val = src.partition(":")
            if kind != "local":
                d0 = up / f"dl_{len(paths)}"
                val = str(P.download(src, d0))
            paths.append(val)
        items = [(f"مونتاج {len(paths)} فيديوهات", "merge:" + "|".join(paths))]
    voice = voice or voices()[0][1]
    now = time.time()
    with db() as c:
        for i, (name, src) in enumerate(items):
            c.execute("INSERT INTO jobs(id,batch,name,source,product_info,instruction,voice,auto_approve,"
                      "make_images,status,step,img_status,created,updated,opts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex[:10], batch, name, src, product_info, instruction, voice,
                       1 if auto_approve else 0, 1 if make_images else 0, "queued", "", "", now + i * 1e-3, now,
                       json.dumps({"subs": 1 if opt_subs else 0, "music": opt_music or "none",
                                   "sizes": 1 if opt_sizes else 0, "ab": 1 if opt_ab else 0})))
    return RedirectResponse(f"/?batch={batch}", status_code=303)


@app.get("/job/{job_id}")
def job_page(request: Request, job_id: str):
    j = get(job_id)
    d = jdir(job_id)
    ads = sorted(p.name for p in (d / "ads").glob("*.jpg")) if (d / "ads").exists() else []
    return T.TemplateResponse(request, "job.html", {
        "j": j, "voices": voices(), "ads": ads,
        "has_work": bool(list(d.glob("source.*"))), "has_final": (d / "final.mp4").exists(),
        "photo": product_photo(job_id), "own_photo": (d / "product.jpg").exists(),
        "music": music_files(),
        "extras": [n for n in ("final_b.mp4", "final_c.mp4", "final_9x16.mp4", "final_1x1.mp4", "final_4x5.mp4")
                   if (d / n).exists()]})


def _floats(xs):
    out = []
    for x in xs:
        try:
            out.append(float(x))
        except ValueError:
            out.append(0.0)
    return out


@app.post("/job/{job_id}/save")
async def save(request: Request, job_id: str):
    j = get(job_id)
    form = await request.form()
    plan = j["plan"] or {}
    starts, ends, texts = _floats(form.getlist("seg_start")), _floats(form.getlist("seg_end")), form.getlist("seg_text")
    plan["segments"] = [{"start": s, "end": e, "text": t} for s, e, t in zip(starts, ends, texts) if t.strip()]
    cuts = []
    for part in (form.get("cuts") or "").replace("،", ",").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                cuts.append([float(a), float(b)])
            except ValueError:
                pass
    plan["cuts"] = cuts
    plan["speed"] = form.get("speed") or 1.0
    plan["orig_volume"] = form.get("orig_volume") or 0.15
    plan["ad"] = {k: form.get(f"ad_{k}", "") for k in ("headline", "price", "cta", "badge")}
    # لقطات التصاور: إلا ما تبدلش التوقيت كنخليو المربع ديال المنتوج اللي لقا Gemini
    old = {f["t"]: f.get("box") for f in (j["plan"] or {}).get("frames") or []}
    plan["frames"] = [{"t": t, "box": old.get(round(t, 2))}
                      for t in _floats(x for x in (form.get("frames") or "").replace("،", ",").split(",") if x.strip())]
    plan = P.normalize_plan(plan, P.duration(work_video(job_id)))
    action = form.get("action", "save")
    fields = {"plan": plan, "plan_prev": j["plan"], "voice": form.get("voice") or j["voice"],
              "opts": json.dumps(opts_from_form(form))}
    plan["hooks"] = [h.strip() for h in form.getlist("hook") if h.strip()][:2]
    if action == "approve":
        fields["status"] = "approved"
    if action == "images" or (action == "approve" and form.get("with_images")):
        fields["img_status"] = "queued"
    update(job_id, **fields)
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.post("/job/{job_id}/instruct")
def instruct(job_id: str, instruction: str = Form(...)):
    get(job_id)
    update(job_id, pending=instruction.strip(), status="edit_queued", error="")
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.post("/job/{job_id}/undo")
def undo(job_id: str):
    j = get(job_id)
    with db() as c:
        prev = c.execute("SELECT plan_prev FROM jobs WHERE id=?", (job_id,)).fetchone()["plan_prev"]
    if prev:
        update(job_id, plan=json.loads(prev), plan_prev=j["plan"], status="review")
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.post("/job/{job_id}/retry")
def retry(job_id: str):
    j = get(job_id)
    st = "approved" if j["plan"] and j["status"] == "error" and j["step"] == "" and (jdir(job_id) / "edited.mp4").exists() else "queued"
    update(job_id, status=st, error="")
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.post("/job/{job_id}/reanalyze")
def reanalyze(job_id: str):
    update(job_id, status="queued", error="", plan_prev=get(job_id)["plan"])
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.post("/job/{job_id}/delete")
def delete(job_id: str):
    j = get(job_id)
    shutil.rmtree(JOBS / job_id, ignore_errors=True)
    with db() as c:
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return RedirectResponse(f"/?batch={j['batch']}", status_code=303)


@app.post("/batch/{batch}/approve_all")
def approve_all(batch: str):
    with db() as c:
        c.execute("UPDATE jobs SET status='approved', updated=? WHERE batch=? AND status='review'", (time.time(), batch))
    return RedirectResponse(f"/?batch={batch}", status_code=303)


@app.post("/batch/{batch}/instruct")
def instruct_batch(batch: str, instruction: str = Form(...)):
    with db() as c:
        c.execute("UPDATE jobs SET pending=?, status='edit_queued', updated=? WHERE batch=? AND plan IS NOT NULL "
                  "AND status IN ('review','done','error')", (instruction.strip(), time.time(), batch))
    return RedirectResponse(f"/?batch={batch}", status_code=303)


ALLOWED = {"final.mp4", "final.srt", "edited.mp4", "enhanced.mp4", "ads.zip", "final_b.mp4", "final_c.mp4",
           "final_9x16.mp4", "final_1x1.mp4", "final_4x5.mp4"}


@app.post("/music")
async def music_upload(files: list[UploadFile] = File(default=[]), remove: str = Form("")):
    if remove:
        (MUSIC / Path(remove).name).unlink(missing_ok=True)
    for f in files or []:
        if f and f.filename and Path(f.filename).suffix.lower() in MUSIC_EXT:
            with open(MUSIC / Path(f.filename).name, "wb") as out:
                shutil.copyfileobj(f.file, out)
    return RedirectResponse("/#music", status_code=303)


@app.post("/job/{job_id}/photo")
async def job_photo(job_id: str, photo: UploadFile | None = File(None), remove: str = Form("")):
    p = jdir(Path(job_id).name) / "product.jpg"
    if remove:
        p.unlink(missing_ok=True)
    elif photo and photo.filename:
        save_photo(await photo.read(), p)
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.get("/files/{job_id}/{name}")
def files(job_id: str, name: str, dl: int = 0):
    d = JOBS / Path(job_id).name
    if name == "source":
        src = sorted(d.glob("source.*"))
        if not src:
            raise HTTPException(404)
        return FileResponse(src[0])
    if name == "product.jpg":
        p = product_photo(Path(job_id).name)
        if not p:
            raise HTTPException(404)
        return FileResponse(p)
    if name == "ads.zip":
        p = d / "ads" / "ads.zip"
    elif name.endswith(".jpg"):
        p = d / "ads" / Path(name).name
    elif name in ALLOWED:
        p = d / name
    else:
        raise HTTPException(404)
    if not p.exists():
        raise HTTPException(404)
    j = get(job_id)
    fname = f"{Path(j['name']).stem}_{name}" if dl else None
    return FileResponse(p, filename=fname)


@app.get("/api/jobs")
def api_jobs(batch: str = ""):
    return JSONResponse([{"id": j["id"], "status": j["status"], "step": j["step"], "img": j["img_status"]}
                         for j in list_jobs(batch or None)])
