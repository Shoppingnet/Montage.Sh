"""خطوات المعالجة: تحميل ← فحص الوضوح ← توضيح ← تحليل وسكريبت ← أوامر التعديل ← صوت ← مونتاج."""
import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

MOCK = os.getenv("MOCK", "0") == "1"
# سرعة الضغط ديال الفيديو: veryfast أسرع بزاف فالسيرفرات الصغار (الجودة كتبقا مزيانة بـ CRF)
PRESET = os.getenv("FFMPEG_PRESET", "veryfast")
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp", ".mpeg", ".mpg"}


# ───────────────────────── أدوات عامة ─────────────────────────
def run(cmd):
    # حد أقصى للوقت: إلا تبلوكا FFmpeg كتطلع غلطة بلاصة ما يبقا الفيديو "كيتصاوب" ديما
    try:
        # nice: FFmpeg كياخد غير المعالج اللي بقا، والصفحة كتبقا كتجاوب ديما
        if cmd and cmd[0] == "ffmpeg":
            cmd = ["nice", "-n", "15", *cmd[:1], "-threads", os.getenv("FFMPEG_THREADS", "2"), *cmd[1:]]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=int(os.getenv("FFMPEG_TIMEOUT", "2400")))
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg طوّل بزاف وتوقف (الفيديو طويل ولا السيرفر مضغوط). جرب فيديو أقصر.")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {r.stderr[-800:]}")
    return r.stdout


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.strip())


def has_audio(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)])
    return bool(out.strip())


def video_size(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)])
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


# ───────────────────────── الروابط و Drive ─────────────────────────
URL_RE = re.compile(r"https?://[^\s,;\"'<>]+")


def extract_links(path: Path):
    """كيقرا ملف txt / csv / xlsx وكيرجع جميع الروابط اللي فيه."""
    text = ""
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                parts += [str(c) for c in row if c]
        text = "\n".join(parts)
    else:
        text = path.read_text(errors="ignore")
    seen, links = set(), []
    for u in URL_RE.findall(text):
        u = u.rstrip(").]")
        if u not in seen:
            seen.add(u)
            links.append(u)
    return links


def classify_link(url):
    m = re.search(r"/folders/([\w-]+)", url)
    if m:
        return "folder", m.group(1)
    m = re.search(r"/file/d/([\w-]+)", url) or re.search(r"[?&]id=([\w-]+)", url)
    if m and "drive.google" in url or (m and "docs.google" in url):
        return "file", m.group(1)
    return "url", url


def list_drive_folder(folder_id):
    """كيرجع [(file_id, name)] ديال الفيديوهات فدوسي Drive عمومي."""
    import gdown
    files = gdown.download_folder(id=folder_id, skip_download=True, quiet=True) or []
    out = []
    for f in files:
        name = Path(f.path).name
        if Path(name).suffix.lower() in VIDEO_EXT:
            out.append((f.id, name))
    return out


def download(source, out_dir: Path):
    """source: 'drive:<id>' ولا 'url:<link>' ولا 'local:<path>'. كيرجع المسار."""
    out_dir.mkdir(parents=True, exist_ok=True)
    kind, _, val = source.partition(":")
    if kind == "merge":  # بزاف ديال الفيديوهات كيتجمعو فواحد
        dst = out_dir / "source.mp4"
        merge_videos([Path(x) for x in val.split("|")], dst)
        return dst
    if kind == "local":
        dst = out_dir / ("source" + Path(val).suffix.lower())
        shutil.copy(val, dst)
        return dst
    if kind == "drive":
        import gdown
        tmp = out_dir / "dl"
        tmp.mkdir(exist_ok=True)
        p = gdown.download(id=val, output=str(tmp) + "/", quiet=True)
        if not p:
            raise RuntimeError("ماقدرش يحمّل من Drive — تأكد أن الفيديو مفتوح بـ Anyone with the link")
        p = Path(p)
        dst = out_dir / ("source" + p.suffix.lower())
        shutil.move(p, dst)
        shutil.rmtree(tmp, ignore_errors=True)
        return dst
    # رابط مباشر
    dst = out_dir / "source.mp4"
    with requests.get(val, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dst, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dst


# ───────────────────────── الوضوح ─────────────────────────
def blur_score(path, samples=12):
    """كلما كان الرقم صغير كلما كان الفيديو مضبب (Laplacian variance)."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    scores = []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (i + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        if w > 720:
            frame = cv2.resize(frame, (720, int(h * 720 / w)))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scores.append(cv2.Laplacian(gray, cv2.CV_64F).var())
    cap.release()
    if not scores:
        return 0.0
    scores.sort()
    return float(scores[len(scores) // 2])


def needs_enhance(path):
    score = blur_score(path)
    w, h = video_size(path)
    threshold = float(os.getenv("BLUR_THRESHOLD", "100"))
    low_res = (os.getenv("ENHANCE_LOW_RES", "0") == "1"
               and min(w, h) < int(os.getenv("MIN_SHORT_SIDE", "720")))
    return score, (score < threshold or low_res)


def enhance(src: Path, out: Path):
    """Real-ESRGAN إلا كان مثبت، وإلا تحسين FFmpeg (تكبير + توضيح خفيف)."""
    target = int(os.getenv("TARGET_SHORT_SIDE", "1080"))
    w, h = video_size(src)
    if shutil.which("realesrgan-ncnn-vulkan"):
        work = out.parent / "esr"
        (work / "in").mkdir(parents=True, exist_ok=True)
        (work / "out").mkdir(parents=True, exist_ok=True)
        fps = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=r_frame_rate", "-of", "csv=p=0", str(src)]).strip()
        run(["ffmpeg", "-y", "-i", str(src), str(work / "in" / "%06d.png")])
        run(["realesrgan-ncnn-vulkan", "-i", str(work / "in"), "-o", str(work / "out"),
             "-n", os.getenv("ESRGAN_MODEL", "realesr-animevideov3"), "-s", "2"])
        cmd = ["ffmpeg", "-y", "-framerate", fps, "-i", str(work / "out" / "%06d.png")]
        if has_audio(src):
            cmd += ["-i", str(src), "-map", "0:v", "-map", "1:a", "-c:a", "copy"]
        cmd += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
        run(cmd)
        shutil.rmtree(work, ignore_errors=True)
        return "realesrgan"
    short = min(w, h)
    scale = max(1.0, target / short)
    nw, nh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    vf = f"scale={nw}:{nh}:flags=lanczos,hqdn3d=1.5:1.5:6:6,unsharp=5:5:1.0:5:5:0.0"
    cmd = ["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-crf", "18",
           "-preset", PRESET, "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "copy"] if has_audio(src) else ["-an"]
    run(cmd + [str(out)])
    return "ffmpeg"


# ───────────────────────── Gemini ─────────────────────────
PLAN_SCHEMA_TEXT = """
رجّع JSON فقط بهاد الشكل:
{
  "product": "سمية المنتوج",
  "cuts": [[بداية, نهاية], ...],      // أجزاء من الفيديو الأصلي اللي خاصها تتحيد (بالثواني). [] إلا ماكاين حتى قص
  "speed": 1.0,                       // سرعة الفيديو (0.5 حتى 2.0)
  "orig_volume": 0.15,                // صوت الفيديو الأصلي تحت التعليق (0 = مقطوع، 1 = كامل)
  "segments": [
    {"start": 0.0, "end": 3.0, "scene": "شنو كيبان فاللقطة", "text": "الجملة بالدارجة"}
  ],
  "frames": [{"t": 4.2, "box": [ymin, xmin, ymax, xmax]}],  // 2 حتى 3 لقطات للتصاور الإعلانية (شوف القواعد التحت)
  "hooks": ["جملة بداية بديلة 1", "جملة بداية بديلة 2"],  // 2 hooks مختلفين (أسلوب آخر) بلاصة الجملة الأولى، للتجربة A/B
  "text_boxes": [{"start": 0.0, "end": 12.0, "box": [ymin, xmin, ymax, xmax]}],  // كتابة مطبوعة فالفيديو (صينية، إنجليزية، لوغو، ترجمة...) باش نمسحوها. [] إلا ماكاينة
  "ad": {"headline": "عنوان قصير وقوي للتصويرة (4 حتى 7 كلمات)", "price": "الثمن بالأرقام مثلا 199 درهم، ولا خاوي إلا ماكانش", "cta": "اطلب دابا", "badge": "الخلاص عند الاستلام"},
  "notes": "شرح قصير بالدارجة لشنو تبدل"
}
- جميع التوقيتات ديال segments و cuts و frames كتكون على التوقيت ديال الفيديو الأصلي (قبل القص والتسريع).
- frames: ختار اللحظات فين المنتوج باين كامل، كبير، واضح وماشي مضبب، وماكاينش شي حاجة مغطياه
  (ماشي لقطة فيها غير شخص كيستعمل المنتوج من بعيد، وماشي لقطة كحلة ولا فيها انتقال).
  ختار لقطات مختلفة (زوايا ولا ألوان مختلفة إلا كانت). box هو المربع اللي فيه المنتوج فداك اللقطة،
  بالأرقام من 0 حتى 1000 بهاد الترتيب: [ymin, xmin, ymax, xmax].
- text_boxes: أي كتابة مطبوعة فوق الفيديو (ترجمة صينية ولا إنجليزية، لوغو، ووترمارك، ثمن، سمية متجر...).
  لكل وحدة: من فوقاش حتى فوقاش كتبان (start/end بالثواني) والمربع اللي كتشغلو [ymin, xmin, ymax, xmax] من 0 حتى 1000،
  مع هامش صغير على الجوانب. إلا كانت الترجمة الصينية كتبدل الجمل ولكن ديما فنفس البلاصة، رجّع مربع واحد كيغطي الزونة كاملة طول الفيديو.
  ماتحطش المنتوج ولا الكتابة اللي على المنتوج نفسو (الباكاج) فـ text_boxes.
"""

SCRIPT_RULES = """
القواعد ديال التعليق:
- دارجة مغربية واضحة بالحروف العربية، بحال شي واحد مغربي كيهضر فإعلان، ماشي فصحى وماشي فرنسية.
- كل جملة مربوطة بلقطة: الجملة كتوصف ولا كتبيع داكشي اللي كيبان فديك اللحظة بالضبط.
- الطول: ماتفوتش تقريبا 2.5 كلمات فالثانية ديال اللقطة، باش الصوت يدخل فالوقت.
- البداية: hook قوي فأول 3 ثواني. النهاية: دعوة للطلب (مثلا: "طلب دابا، والخلاص ملي توصلك السلعة").
- ماتخترعش مميزات ولا أثمنة ماكايناش فالفيديو ولا فالمعلومات اللي عطاك المستعمل.
- كتب الأرقام بالحروف إلا كانت ثمن (مثلا "ميا وتسعة وتسعين درهم") باش تتنطق مزيان.
"""


def _gemini_client():
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def normalize_plan(plan, dur):
    plan.setdefault("product", "")
    plan["speed"] = min(2.0, max(0.5, float(plan.get("speed") or 1.0)))
    plan["orig_volume"] = min(1.0, max(0.0, float(plan.get("orig_volume", os.getenv("ORIG_VOLUME", "0.15")))))
    cuts = []
    for c in plan.get("cuts") or []:
        s, e = max(0.0, float(c[0])), min(dur, float(c[1]))
        if e - s > 0.05:
            cuts.append([s, e])
    cuts.sort()
    merged = []
    for s, e in cuts:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    plan["cuts"] = merged
    segs = []
    for s in plan.get("segments") or []:
        st, en = max(0.0, float(s["start"])), min(dur, float(s["end"]))
        if en > st and str(s.get("text", "")).strip():
            segs.append({"start": round(st, 2), "end": round(en, 2),
                         "scene": s.get("scene", ""), "text": s["text"].strip()})
    plan["segments"] = sorted(segs, key=lambda x: x["start"])
    frames = []
    for fr in plan.get("frames") or []:
        try:
            t = min(max(0.0, float(fr["t"])), max(0.0, dur - 0.05))
        except (KeyError, TypeError, ValueError):
            continue
        box = fr.get("box")
        try:
            box = [min(1000.0, max(0.0, float(v))) for v in box]
            if len(box) != 4 or box[2] - box[0] < 20 or box[3] - box[1] < 20:
                box = None
        except (TypeError, ValueError):
            box = None
        frames.append({"t": round(t, 2), "box": box})
    plan["frames"] = frames[:4]
    plan["hooks"] = [str(x).strip() for x in (plan.get("hooks") or []) if str(x).strip()][:2]
    plan["text_boxes"] = normalize_boxes(plan.get("text_boxes"), dur)
    ad = plan.get("ad") or {}
    plan["ad"] = {"headline": ad.get("headline") or plan["product"], "price": ad.get("price") or "",
                  "cta": ad.get("cta") or "اطلب دابا", "badge": ad.get("badge") or "الخلاص عند الاستلام"}
    return plan


def normalize_boxes(boxes, dur):
    out = []
    for tb in boxes or []:
        try:
            a, b = max(0.0, float(tb.get("start", 0))), min(dur, float(tb.get("end", dur)))
            box = [min(1000.0, max(0.0, float(v))) for v in tb["box"]]
            if len(box) != 4 or box[2] - box[0] < 10 or box[3] - box[1] < 10 or b - a < 0.2:
                continue
            out.append({"start": round(a, 2), "end": round(b, 2), "box": [round(v) for v in box]})
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out[:8]


def clean_filter(boxes, w, h, cuts=(), speed=1.0, pad=0.012):
    """فلتر FFmpeg كيمسح الكتابة المطبوعة (delogo) فالمربعات وفالوقت ديالها. كيرجع لائحة فلاتر."""
    out = []
    for tb in boxes or []:
        y0, x0, y1, x1 = tb["box"]
        x = max(1, int((x0 / 1000 - pad) * w)); y = max(1, int((y0 / 1000 - pad) * h))
        bw = min(w - x - 1, int((x1 - x0) / 1000 * w + 2 * pad * w)); bh = min(h - y - 1, int((y1 - y0) / 1000 * h + 2 * pad * h))
        if bw < 4 or bh < 4:
            continue
        a, b = map_time(tb["start"], cuts, speed), map_time(tb["end"], cuts, speed)
        if b - a < 0.1:
            continue
        out.append(f"delogo=x={x}:y={y}:w={bw}:h={bh}:enable='between(t,{a:.2f},{b + 0.05:.2f})'")
    return out


def find_text_boxes(video: Path):
    """وضع كابشن: Gemini كيقلب غير على الكتابة المطبوعة فالفيديو (بلا سكريبت)."""
    dur = duration(video)
    if MOCK:
        return normalize_boxes([{"start": 0, "end": dur, "box": [880, 100, 960, 900]}], dur)
    from google.genai import types
    client = _gemini_client()
    f = client.files.upload(file=str(video))
    while f.state and f.state.name == "PROCESSING":
        time.sleep(3)
        f = client.files.get(name=f.name)
    if f.state and f.state.name == "FAILED":
        raise RuntimeError("Gemini ماقدرش يقرا الفيديو")
    prompt = f"""شوف هاد الفيديو (الطول {dur:.1f} ثانية) وقلب على أي كتابة مطبوعة فوقو: ترجمة صينية ولا إنجليزية،
لوغو، ووترمارك، سمية متجر، ثمن... (ماشي الكتابة اللي على المنتوج نفسو).
لكل وحدة رجّع من فوقاش حتى فوقاش كتبان والمربع اللي كتشغلو [ymin, xmin, ymax, xmax] من 0 حتى 1000 مع هامش صغير.
إلا كانت الترجمة كتبدل ولكن ديما فنفس البلاصة، رجّع مربع واحد كيغطي الزونة كاملة طول الفيديو.
رجّع JSON فقط: {{"text_boxes": [{{"start": 0.0, "end": {dur:.1f}, "box": [ymin, xmin, ymax, xmax]}}]}} ([] إلا ماكاينة)"""
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"), contents=[f, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
    )
    try:
        client.files.delete(name=f.name)
    except Exception:
        pass
    return normalize_boxes(_parse_json(resp.text).get("text_boxes"), dur)


def analyze(video: Path, product_info="", instruction="", photo=None):
    """Gemini كيشوف الفيديو وكيكتب السكريبت مقسم + كيطبق الأمر ديال الدفعة إلا كاين."""
    dur = duration(video)
    if MOCK:
        n = max(1, int(dur // 3))
        segs = [{"start": i * dur / n, "end": (i + 1) * dur / n, "scene": "لقطة",
                 "text": f"هادي الجملة رقم {i+1} على المنتوج"} for i in range(n)]
        return normalize_plan({"product": "منتوج", "cuts": [], "speed": 1.0, "segments": segs,
                               "ad": {"headline": "كرسي مريح للظهر بجودة عالية", "price": "199 درهم"},
                               "frames": [{"t": dur * 0.3, "box": [200, 250, 800, 750]}, {"t": dur * 0.7, "box": None}],
                               "hooks": ["جملة بداية بديلة واحد", "جملة بداية بديلة جوج"],
                               "text_boxes": [{"start": 0, "end": dur, "box": [880, 100, 960, 900]}],
                               "notes": "تجربة"}, dur)
    from google.genai import types
    from PIL import Image
    client = _gemini_client()
    f = client.files.upload(file=str(video))
    while f.state and f.state.name == "PROCESSING":
        time.sleep(3)
        f = client.files.get(name=f.name)
    if f.state and f.state.name == "FAILED":
        raise RuntimeError("Gemini ماقدرش يقرا الفيديو")
    prompt = f"""نتا مونتور ومعلق صوتي محترف ديال إعلانات e-commerce فالمغرب (الدفع عند الاستلام).
شوف هاد الفيديو ديال المنتوج (الطول: {dur:.1f} ثانية)، وقسمو على اللقطات، واكتب تعليق صوتي بالدارجة كيمشي مع الحركة.
{SCRIPT_RULES}
معلومات على المنتوج من المستعمل: {product_info or "ماكاينش"}
أمر من المستعمل (طبقو إلا كان): {instruction or "ماكاينش"}
{"التصويرة اللي مع الفيديو هي تصويرة المنتوج: استعملها باش تعرف المنتوج وتلقاه فالفيديو (frames و box)." if photo else ""}
{PLAN_SCHEMA_TEXT}"""
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        contents=[f] + ([Image.open(photo)] if photo else []) + [prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7),
    )
    try:
        client.files.delete(name=f.name)
    except Exception:
        pass
    return normalize_plan(_parse_json(resp.text), dur)


TRANSCRIBE_RULES = """- الدارجة والعربية بالحروف العربية كيف ما تنطقات بالضبط (ماتترجمش، ماتصححش للفصحى، ماتحيدش التكرار ولا "ايوا"/"يعني").
- الكلمات بالفرنسية ولا الإنجليزية خليها بالحروف اللاتينية كيف ما تنطقات (ماتكتبهاش بالعربية).
- الأرقام اكتبها بالأرقام (199).
- التوقيت بالثواني بدقة (s = البداية، e = النهاية) من بداية هاد المقطع، ماتخليش فراغات كبار بين الكلمات."""


def _silence_chunks(wav: Path, dur, max_len=30.0, min_len=8.0):
    """كيقطع الصوت لمقاطع 8-30 ثانية عند السكوت (ماشي وسط كلمة): Gemini كيعطي توقيت أدق على مقاطع قصار."""
    if dur <= max_len:
        return [(0.0, dur)]
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(wav), "-af", "silencedetect=noise=-35dB:d=0.3", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600)
    out = r.stderr
    sil = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", out)]
    mids = sorted((a + b) / 2 for a, b in zip(sil, ends) if b > a)
    chunks, start = [], 0.0
    for m in mids:
        if m - start >= min_len:
            chunks.append((start, m))
            start = m
        elif m - start > max_len:
            chunks.append((start, start + max_len))
            start = start + max_len
    while dur - start > max_len:
        chunks.append((start, start + max_len))
        start += max_len
    if dur - start > 0.3:
        chunks.append((start, dur))
    return chunks


def transcribe(video: Path):
    """وضع 'كابشن': واحد كيهضر فالفيديو. Gemini كيسمع كل مقطع (8-30 ثانية) وكيرجع كل كلمة مع التوقيت ديالها.
    من بعد (اختياري WHISPERX=1) forced alignment محلي كيدقق توقيت كل كلمة على الصوت."""
    dur = duration(video)
    if MOCK:
        words = "سلام عليكم هاد المنتوج زوين بزاف و الثمن غير ميا و تسعة و تسعين درهم".split()
        step = dur / len(words)
        return [{"w": w, "s": round(i * step, 2), "e": round((i + 1) * step, 2)} for i, w in enumerate(words)]
    from google.genai import types
    client = _gemini_client()
    wav = video.with_name("speech16k.wav")
    run(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    out = []
    for a, b in _silence_chunks(wav, dur):
        part = video.with_name("chunk.wav")
        run(["ffmpeg", "-y", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(wav), str(part)])
        prompt = f"""اسمع الكلام اللي فهاد المقطع الصوتي (الطول {b - a:.1f} ثانية، كيبدا فالثانية {a:.1f} من الفيديو) واكتبو كلمة بكلمة كيف ما تنطق بالضبط مع التوقيت ديال كل كلمة.
{TRANSCRIBE_RULES}
رجّع JSON فقط: {{"words": [{{"w": "الكلمة", "s": 0.0, "e": 0.4}}, ...]}} ([] إلا ماكاين حتى كلام)"""
        resp = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            contents=[types.Part.from_bytes(data=part.read_bytes(), mime_type="audio/wav"), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
        )
        for w in _parse_json(resp.text).get("words") or []:
            try:
                s_, e = float(w["s"]) + a, float(w["e"]) + a
                if str(w.get("w", "")).strip() and e > s_ >= 0:
                    out.append({"w": str(w["w"]).strip(), "s": round(min(s_, dur), 2), "e": round(min(e, dur), 2)})
            except (KeyError, TypeError, ValueError):
                continue
        part.unlink(missing_ok=True)
    if not out:
        raise RuntimeError("Gemini مالقا حتى كلام فالفيديو")
    out.sort(key=lambda x: x["s"])
    if os.getenv("WHISPERX", "0") == "1":
        try:
            import align
            out = align.refine(wav, out)
        except Exception as e:  # noqa: whisperx ماشي ضروري، إلا طاح كنخليو توقيت Gemini
            print("whisperx alignment skipped:", e)
    return out


def words_to_segments(words, gap=0.7, max_words=10):
    """كيقسم الكلمات لجمل (للمراجعة فالصفحة): جملة جديدة ملي كاين سكوت ولا كتوصل لـ 10 كلمات."""
    segs, cur = [], []
    for w in words:
        if cur and (w["s"] - cur[-1]["e"] > gap or len(cur) >= max_words):
            segs.append(cur)
            cur = []
        cur.append(w)
    if cur:
        segs.append(cur)
    return [{"start": c[0]["s"], "end": c[-1]["e"], "text": " ".join(x["w"] for x in c)} for c in segs]


def render_captions(src: Path, segments, work: Path, out: Path, music: Path = None, orig_volume=1.0, boxes=None):
    """وضع كابشن: نفس الفيديو ونفس الصوت الأصلي + الترجمة كلمة بكلمة (+ موسيقى اختيارية)."""
    w, h = video_size(src)
    cap = int(os.getenv("MAX_SHORT_SIDE", "1080"))
    if min(w, h) > cap:
        k = cap / min(w, h)
        w, h = int(w * k) // 2 * 2, int(h * k) // 2 * 2
    placed = [{"text": s_["text"], "start": s_["start"], "end": s_["end"], "words": s_.get("words")} for s_ in segments]
    ass = work / "subs.ass"
    write_ass(placed, ass, w, h)
    total = duration(src)
    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
    vf = [f"scale={w}:{h}", "setsar=1", *clean_filter(boxes, w, h),
          f"ass='{ass}':fontsdir='{Path(__file__).parent / 'fonts'}'", "format=yuv420p"]
    filt = ["[0:v]" + ",".join(vf) + "[v]"]
    if has_audio(src):
        if music:
            mv = float(os.getenv("MUSIC_VOLUME", "0.18"))
            filt.append(f"[0:a]volume={orig_volume:.3f},asplit=2[vo][sc]")
            filt.append(f"[1:a]volume={mv:.3f},aresample=44100,aformat=channel_layouts=stereo[m]")
            filt.append("[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md]")
            filt.append("[vo][md]amix=inputs=2:duration=first:normalize=0[a]")
        else:
            filt.append(f"[0:a]volume={orig_volume:.3f}[a]")
        amap = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    else:
        amap = ["-an"]
    run(cmd + ["-filter_complex", ";".join(filt), "-map", "[v]", *amap, "-c:v", "libx264", "-crf", "21",
               "-preset", PRESET, "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    return placed


def apply_instruction(plan, instruction, dur, product_info=""):
    """كياخد أمر بالدارجة (قص، سرّع، بدل الجملة...) وكيرجع plan جديد."""
    if MOCK:
        p = json.loads(json.dumps(plan))
        if "سرع" in instruction or "سرّع" in instruction:
            p["speed"] = 1.25
        m = re.search(r"قص.*?(\d+(?:\.\d+)?)", instruction)
        if m:
            p["cuts"] = [[0, float(m.group(1))]]
        p["notes"] = "تجربة: " + instruction
        return normalize_plan(p, dur)
    from google.genai import types
    client = _gemini_client()
    prompt = f"""نتا مونتور محترف. هادا هو plan الحالي ديال فيديو طولو {dur:.1f} ثانية:
{json.dumps(plan, ensure_ascii=False, indent=1)}

معلومات على المنتوج: {product_info or "ماكاينش"}
الأمر ديال المستعمل بالدارجة: «{instruction}»

طبّق الأمر على plan:
- "قص/حيد من X حتى Y" ← زيد فـ cuts (التوقيت ديال الفيديو الأصلي). "قص البداية/الأولى X ثواني" ← [0, X].
- "سرّع/بطّأ" ← بدل speed (سرّع شوية = 1.15، سرّع = 1.25، سرّع بزاف = 1.5).
- "بدل/صلح/زيد الجملة..." ← بدل segments. إلا قال "اكتب السكريبت من جديد" عاود كتبو كامل.
- "نقص/حيد صوت الفيديو" ← orig_volume.
- "بدل التصويرة / خود اللقطة ديال الثانية X" ← بدل frames (وحط box ديال المنتوج إلا كان باين فـ scene).
- إلا قصيتي شي جزء، حيد ولا عدّل الجمل اللي كانت فيه.
- خلي كلشي آخر كيف ما هو. ماتبدلش حوايج ماطلبهاش.
{SCRIPT_RULES}
{PLAN_SCHEMA_TEXT}"""
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        contents=[prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4),
    )
    return normalize_plan(_parse_json(resp.text), dur)


# ───────────────────────── القص والتسريع ─────────────────────────
def keep_ranges(cuts, dur):
    ranges, t = [], 0.0
    for s, e in cuts:
        if s > t:
            ranges.append((t, s))
        t = max(t, e)
    if t < dur:
        ranges.append((t, dur))
    return ranges or [(0.0, dur)]


def map_time(t, cuts, speed):
    """كيحول وقت من الفيديو الأصلي للفيديو بعد القص والتسريع."""
    removed = 0.0
    for s, e in cuts:
        if t >= e:
            removed += e - s
        elif t > s:
            removed += t - s
            break
    return (t - removed) / speed


def render_final(src: Path, plan, voice_id, work: Path, out: Path, subs=True, music: Path = None, clean=True):
    """كلشي فـ encode واحد: القص + التسريع + التعليق + الموسيقى + الترجمة. (أسرع جوج حتى 3 مرات)"""
    dur = duration(src)
    ranges = keep_ranges(plan["cuts"], dur)
    speed = plan["speed"]
    edited_dur = sum(e - s_ for s_, e in ranges) / speed
    voice, placed, total = build_voice_track(plan, voice_id, edited_dur, work)
    audio = has_audio(src)
    w, h = video_size(src)
    cap = int(os.getenv("MAX_SHORT_SIDE", "1080"))
    if min(w, h) > cap:
        k = cap / min(w, h)
        w, h = int(w * k) // 2 * 2, int(h * k) // 2 * 2
    cmd, filt = ["ffmpeg", "-y"], []
    for s_, e in ranges:
        cmd += ["-ss", f"{s_:.3f}", "-t", f"{e - s_:.3f}", "-i", str(src)]
    n = len(ranges)
    cmd += ["-i", str(voice)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
    labels = "".join(f"[{i}:v]" + (f"[{i}:a]" if audio else "") for i in range(n))
    filt.append(labels + f"concat=n={n}:v=1:a={1 if audio else 0}[vc]" + ("[ac]" if audio else ""))
    vf = [f"setpts=PTS/{speed:.4f}", f"scale={w}:{h}", "setsar=1"]
    if clean:
        vf += clean_filter(plan.get("text_boxes"), w, h, plan["cuts"], speed)
    if total - edited_dur > 0.05:
        vf.append(f"tpad=stop_mode=clone:stop_duration={total - edited_dur + 0.3:.3f}")
    if subs:
        ass = work / "subs.ass"
        write_ass(placed, ass, w, h)
        vf.append(f"ass='{ass}':fontsdir='{Path(__file__).parent / 'fonts'}'")
    filt.append("[vc]" + ",".join(vf) + ",format=yuv420p[v]")
    mix = ["[vo]"]
    if music:
        filt.append(f"[{n}:a]asplit=2[vo][sc]")
        mv = float(plan.get("music_volume", os.getenv("MUSIC_VOLUME", "0.22")))
        filt.append(f"[{n + 1}:a]volume={mv:.3f},aresample=44100,aformat=channel_layouts=stereo[m]")
        filt.append("[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md]")
        mix.append("[md]")
    else:
        filt.append(f"[{n}:a]anull[vo]")
    vol = plan["orig_volume"]
    if audio and vol > 0.001:
        filt.append(f"[ac]{_atempo_chain(speed)},volume={vol:.3f},aresample=44100,apad[bg]")
        mix.append("[bg]")
    elif audio:
        filt.append("[ac]anullsink")
    filt.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0[a]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "21", "-preset", PRESET, "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)]
    run(cmd)
    return placed, total


def render_edit(src: Path, plan, out: Path):
    """كيطبق القص والتسريع على الفيديو (والصوت الأصلي)."""
    dur = duration(src)
    ranges = keep_ranges(plan["cuts"], dur)
    speed = plan["speed"]
    audio = has_audio(src)
    if len(ranges) == 1 and ranges[0] == (0.0, dur) and abs(speed - 1) < 1e-3:
        shutil.copy(src, out)
        return
    # كل جزء كيتقرا كـ input بوحدو (-ss/-t): FFmpeg مكيخزنش التصاور فالذاكرة.
    # (trim على نفس [0:v] بزاف ديال المرات كان كيخزن الفيديو كامل وكيغرق السيرفر)
    cmd, labels = ["ffmpeg", "-y"], []
    for s_, e_ in ranges:
        cmd += ["-ss", f"{s_:.3f}", "-t", f"{e_ - s_:.3f}", "-i", str(src)]
    for i in range(len(ranges)):
        labels.append(f"[{i}:v]" + (f"[{i}:a]" if audio else ""))
    n = len(ranges)
    parts = ["".join(labels) + f"concat=n={n}:v=1:a={1 if audio else 0}[vc]" + ("[ac]" if audio else "")]
    parts.append(f"[vc]setpts=PTS/{speed:.4f}[vo]")
    if audio:
        parts.append(f"[ac]{_atempo_chain(speed)}[ao]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vo]"]
    cmd += ["-map", "[ao]", "-c:a", "aac", "-b:a", "160k"] if audio else ["-an"]
    run(cmd + ["-c:v", "libx264", "-crf", "19", "-preset", PRESET, "-pix_fmt", "yuv420p", str(out)])


def _atempo_chain(f):
    f = max(0.5, min(f, 4.0))
    steps = []
    while f > 2.0:
        steps.append(2.0)
        f /= 2.0
    while f < 0.5:
        steps.append(0.5)
        f /= 0.5
    steps.append(f)
    return ",".join(f"atempo={x:.4f}" for x in steps) if steps else "anull"


# ───────────────────────── الصوت (ElevenLabs) ─────────────────────────
def tts(text, voice_id, out: Path):
    """voice_id: 'gemini:<VoiceName>' كيستعمل Gemini TTS (رخيص)، وأي حاجة أخرى = ElevenLabs."""
    if not MOCK and voice_id.startswith("gemini:"):
        return gemini_tts(text, voice_id.split(":", 1)[1], out)
    if MOCK:
        secs = max(0.6, len(text.split()) / 2.6)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs:.2f}",
             "-ar", "44100", str(out)])
        return
    import base64
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"},
        json={"text": text, "model_id": os.getenv("ELEVEN_MODEL", "eleven_v4")},
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    data = r.json()
    out.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or {}
    words = words_from_alignment(al.get("characters") or [], al.get("character_start_times_seconds") or [],
                                 al.get("character_end_times_seconds") or [])
    if words:
        out.with_suffix(".words.json").write_text(json.dumps(words, ensure_ascii=False))


def words_from_alignment(chars, starts, ends):
    """كيجمع الحروف لكلمات: [(الكلمة, البداية, النهاية), ...]"""
    words, cur, cs, ce = [], "", None, None
    for ch, a, b in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append((cur, cs, ce))
            cur, cs = "", None
            continue
        if cs is None:
            cs = a
        cur += ch
        ce = b
    if cur:
        words.append((cur, cs, ce))
    return words


_PARTICLES = {"و", "ب", "ف", "ل", "ك", "الـ", "ال", "لا", "ما", "من", "في", "على", "ديال", "د"}


def merge_particles(wt):
    """أدوات قصار (و، ب، ف، الـ...) كتلصق مع الكلمة اللي موراها باش ماتبانش بوحدها فالترجمة."""
    out = []
    i = 0
    while i < len(wt):
        w, a, b = wt[i]
        if (w in _PARTICLES or len(w) == 1) and i + 1 < len(wt):
            w2, _, b2 = wt[i + 1]
            out.append((w + " " + w2, a, b2))
            i += 2
        else:
            out.append((w, a, b))
            i += 1
    return out


def _display(w):
    """كلمة لاتينية وسط الدارجة كتبان بالاتجاه الصحيح (ماشي معكوسة)."""
    w = w.replace("{", "(").replace("}", ")")
    return re.sub(r"[A-Za-z][A-Za-z0-9'.-]*", lambda m: "\u2066" + m.group(0) + "\u2069", w)


def word_times(clip_mp3: Path, text, start, end, tempo=1.0, known=None):
    """وقت كل كلمة فالفيديو النهائي. إلا ماكانش عندنا alignment (Gemini TTS / MOCK)، كنقسمو على طول الكلمات."""
    if known:  # وضع كابشن: التوقيت جا من Gemini مباشرة
        return [(x["w"], x["s"], x["e"]) for x in known]
    words = text.split()
    wj = clip_mp3.with_suffix(".words.json") if clip_mp3 else None
    if wj and wj.exists():
        try:
            al = json.loads(wj.read_text())
            if len(al) == len(words):
                return [(w, start + a / tempo, start + b / tempo) for (w, a, b) in al]
        except (ValueError, TypeError):
            pass
    total = sum(len(w) for w in words) or 1
    t, out = start, []
    for w in words:
        d = (end - start) * len(w) / total
        out.append((w, t, t + d))
        t += d
    return out


def gemini_tts(text, voice_name, out: Path):
    import wave
    from google.genai import types
    client = _gemini_client()
    style = os.getenv("GEMINI_TTS_STYLE",
                      "قرا هاد النص بالدارجة المغربية بنطق مغربي طبيعي، بصوت معلق إعلانات حماسي وواضح:")
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts"),
        contents=f"{style}\n{text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name))),
        ),
    )
    pcm = resp.candidates[0].content.parts[0].inline_data.data
    wav = out.with_suffix(".gem.wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    # نحيدو الصمت من البداية والنهاية باش التوقيت يكون دقيق
    run(["ffmpeg", "-y", "-i", str(wav), "-af",
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse", str(out)])
    wav.unlink(missing_ok=True)


def build_voice_track(plan, voice_id, edited_dur, work: Path):
    """كيصاوب صوت لكل جملة وكيحطها فالتوقيت ديال اللقطة ديالها، وكيسرّعها إلا كانت طويلة."""
    max_tempo = float(os.getenv("MAX_TEMPO", "1.25"))
    cuts, speed = plan["cuts"], plan["speed"]
    segs = []
    for s in plan["segments"]:
        a, b = map_time(s["start"], cuts, speed), map_time(s["end"], cuts, speed)
        if b - a > 0.2:
            segs.append({**s, "o_start": a, "o_end": b})
    placed, cursor = [], 0.0
    cache = work.parent / "tts_cache"
    cache.mkdir(exist_ok=True)
    for i, s in enumerate(segs):
        import hashlib
        raw = cache / (hashlib.sha1(f"{voice_id}|{s['text']}".encode()).hexdigest()[:16] + ".mp3")
        if not raw.exists() or raw.stat().st_size == 0:
            tts(s["text"], voice_id, raw)
        d = duration(raw)
        start = max(s["o_start"], cursor)
        next_start = segs[i + 1]["o_start"] if i + 1 < len(segs) else edited_dur
        slot = max(0.3, next_start - start - 0.05)
        clip = work / f"seg{i:02d}.wav"
        tempo = 1.0
        if d > slot:
            tempo = min(d / slot, max_tempo)
        run(["ffmpeg", "-y", "-i", str(raw), "-af", _atempo_chain(tempo) if tempo > 1.001 else "anull",
             "-ar", "44100", "-ac", "2", str(clip)])
        cd = duration(clip)
        placed.append({"file": clip, "start": start, "end": start + cd, "text": s["text"], "raw": raw, "tempo": tempo})
        cursor = start + cd + 0.08
    total = max([edited_dur] + [p["end"] for p in placed])
    if not placed:
        raise RuntimeError("ماكاين حتى جملة فالسكريبت")
    inputs, filt = [], []
    for i, p in enumerate(placed):
        inputs += ["-i", str(p["file"])]
        ms = int(p["start"] * 1000)
        filt.append(f"[{i}:a]adelay={ms}|{ms}[d{i}]")
    filt.append("".join(f"[d{i}]" for i in range(len(placed))) +
                f"amix=inputs={len(placed)}:normalize=0,apad=whole_dur={total:.3f}[out]")
    voice = work / "voice.wav"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[out]", "-ar", "44100", str(voice)])
    return voice, placed, total


def write_srt(placed, path: Path):
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
    lines = []
    for i, p in enumerate(placed, 1):
        lines += [str(i), f"{ts(p['start'])} --> {ts(p['end'])}", p["text"], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_ass(placed, path: Path, w: int, h: int):
    """ترجمة مكتوبة على الفيديو: كل 3-4 كلمات بوحدهم، بخط عريض وحاشية كحلة (بحال CapCut)."""
    def ts(t):
        cs = int(round(t * 100))
        return f"{cs//360000}:{cs//6000%60:02d}:{cs//100%60:02d}.{cs%100:02d}"
    size = int(min(w, h) * float(os.getenv("SUBS_SIZE", "0.095")))
    margin_v = int(h * (0.22 if h / w > 1.3 else 0.1))
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic,"
             " Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment,"
             " MarginL, MarginR, MarginV, Encoding",
             f"Style: D,Cairo,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,"
             f"{max(2, size // 12)},{max(1, size // 25)},2,{int(w*0.06)},{int(w*0.06)},{margin_v},1",
             f"Style: H,Cairo,{size},&H0000D7FF,&H0000D7FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,"
             f"{max(2, size // 12)},{max(1, size // 25)},2,{int(w*0.06)},{int(w*0.06)},{margin_v},1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    n = int(os.getenv("SUBS_WORDS", "3"))
    hi = os.getenv("SUBS_HIGHLIGHT", "1") == "1"
    for p in placed:
        wt = merge_particles(word_times(p.get("raw"), p["text"], p["start"], p["end"], p.get("tempo", 1.0),
                                        p.get("words")))
        if not wt:
            continue
        # كل كلمة كتبقا باينة حتى تبدا اللي موراها (بلا فراغات)
        wt = [(w, a, (wt[i + 1][1] if i + 1 < len(wt) else b)) for i, (w, a, b) in enumerate(wt)]
        groups = [wt[i:i + n] for i in range(0, len(wt), n)]
        for g in groups:
            g_start, g_end = g[0][1], g[-1][2]
            if not hi:
                txt = " ".join(_display(w) for w, _, _ in g)
                lines.append(f"Dialogue: 0,{ts(g_start)},{ts(g_end)},D,,0,0,0,,{txt}")
                continue
            # نفس المجموعة كتبان كاملة، والكلمة اللي كتنطق دابا كتولي صفرا وكبيرة شوية
            for k, (w, a, b) in enumerate(g):
                parts = []
                for j, (w2, _, _) in enumerate(g):
                    w2 = _display(w2)
                    parts.append(f"{{\\c&H0000D7FF&\\fscx108\\fscy108}}{w2}{{\\r}}" if j == k else w2)
                e = b if k < len(g) - 1 else g_end
                lines.append(f"Dialogue: 0,{ts(a)},{ts(max(e, a + 0.05))},D,,0,0,0,,{' '.join(parts)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def final_mix(edited: Path, voice: Path, plan, total, out: Path, subs: Path = None, music: Path = None):
    """كيركب الفيديو + التعليق + صوت الفيديو الأصلي + الموسيقى (كتنقص بوحدها ملي كيهضر) + الترجمة."""
    vdur = duration(edited)
    extra = max(0.0, total - vdur)
    vf = []
    if extra > 0.05:
        vf.append(f"tpad=stop_mode=clone:stop_duration={extra + 0.3:.3f}")
    if subs:
        fonts = str(Path(__file__).parent / "fonts")
        vf.append(f"ass='{subs}':fontsdir='{fonts}'")
    cmd = ["ffmpeg", "-y", "-i", str(edited), "-i", str(voice)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
    filt, mix = [], ["[vo]"]
    vol = plan["orig_volume"]
    if music:
        filt.append("[1:a]asplit=2[vo][sc]")
        mv = float(plan.get("music_volume", os.getenv("MUSIC_VOLUME", "0.22")))
        filt.append(f"[2:a]volume={mv:.3f},aresample=44100[m]")
        filt.append("[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md]")
        mix.append("[md]")
    else:
        filt.append("[1:a]anull[vo]")
    if has_audio(edited) and vol > 0.001:
        filt.append(f"[0:a]volume={vol:.3f},apad[bg]")
        mix.append("[bg]")
    filt.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0[a]")
    if vf:
        filt.append("[0:v]" + ",".join(vf) + "[v]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[v]" if vf else "0:v", "-map", "[a]"]
    cmd += ["-c:v", "libx264", "-crf", "20", "-preset", PRESET, "-pix_fmt", "yuv420p"] if vf else ["-c:v", "copy"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-t", f"{max(total, vdur):.3f}", "-movflags", "+faststart", str(out)]
    run(cmd)


SIZES = {"9x16": (1080, 1920), "1x1": (1080, 1080), "4x5": (1080, 1350)}


def make_sizes(src: Path, out_dir: Path):
    """نفس الفيديو بمقاسات أخرى (TikTok/Reels، فيد مربع، فيد طولاني) بخلفية مضببة."""
    w, h = video_size(src)
    made = {}
    for key, (W, H) in SIZES.items():
        if abs(w / h - W / H) < 0.03:
            continue  # نفس المقاس ديال الفيديو الأصلي
        out = out_dir / f"final_{key}.mp4"
        f = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
             f"boxblur=25:2,eq=brightness=-0.08[bg];[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
             f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")
        run(["ffmpeg", "-y", "-i", str(src), "-filter_complex", f, "-map", "[v]", "-map", "0:a?",
             "-c:v", "libx264", "-crf", "21", "-preset", PRESET, "-c:a", "copy", "-movflags", "+faststart", str(out)])
        made[key] = out
    return made


def merge_videos(srcs, out: Path):
    """كيجمع بزاف ديال الفيديوهات ففيديو واحد (عمودي 1080x1920)، باش يتصاوب منو إعلان واحد."""
    W, H = 1080, 1920
    cmd, parts = ["ffmpeg", "-y"], []
    for p in srcs:
        cmd += ["-i", str(p)]
    for i, p in enumerate(srcs):
        parts.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                     f"setsar=1,fps=30,format=yuv420p[v{i}]")
        if has_audio(p):
            parts.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}]")
        else:
            parts.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{duration(p):.3f}[a{i}]")
    parts.append("".join(f"[v{i}][a{i}]" for i in range(len(srcs))) + f"concat=n={len(srcs)}:v=1:a=1[v][a]")
    run(cmd + ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "20",
               "-preset", PRESET, "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])

# ───────────────────────── صفحات الهبوط ─────────────────────────
LANDING_SCHEMA = """
رجّع JSON فقط بهاد الشكل:
{
  "title": "عنوان الصفحة (hook قوي بالدارجة، 5 حتى 9 كلمات)",
  "subtitle": "جملة تحت العنوان كتوضح الفائدة الرئيسية",
  "angle": "زاوية البيع اللي اخترتي (مثلا: الراحة / التوفير / الهدية / الصحة)",
  "price": "199 درهم", "old_price": "299 درهم ولا خاوي",
  "cta": "اطلب دابا والخلاص عند الاستلام",
  "problem": "فقرة قصيرة كتوصف المشكل اللي كيعيشو الزبون",
  "solution": "فقرة قصيرة كيفاش المنتوج كيحل المشكل",
  "benefits": [{"icon": "✅", "title": "فائدة", "text": "شرح قصير"}],   // 4 حتى 6
  "how": ["خطوة 1", "خطوة 2", "خطوة 3"],
  "social": [{"name": "سمية مغربية", "city": "مدينة", "text": "رأي قصير بالدارجة"}],  // 3
  "faq": [{"q": "سؤال", "a": "جواب"}],   // 4 حتى 5 (التوصيل، الخلاص، الضمان، الاستعمال...)
  "urgency": "جملة قصيرة كتحمس (العرض محدود / الكمية قليلة...)",
  "guarantee": "جملة الضمان / الإرجاع"
}
"""


def _claude_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _image_block(photo):
    import base64
    from io import BytesIO
    from PIL import Image
    im = Image.open(photo).convert("RGB")
    im.thumbnail((1200, 1200))
    buf = BytesIO()
    im.save(buf, "JPEG", quality=85)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


LANDING_SYSTEM = """نتا كوبيرايتر محترف ديال صفحات الهبوط للتجارة الإلكترونية فالمغرب (الدفع عند الاستلام، الزبون كيقرا فالتلفون).
كتكتب بالدارجة المغربية بالحروف العربية، بحال شي واحد مغربي كيهضر مع صاحبو: ماشي فصحى، ماشي ترجمة حرفية.
القواعد:
- hook قوي فالعنوان، كيهضر على الفائدة ولا المشكل، ماشي على المنتوج.
- جمل قصار. فقرة = 2 حتى 3 جمل. بلا حشو.
- ماتخترعش مميزات ولا أرقام ماكايناش فالمعلومات. إلا ماكانش الثمن خلي price خاوي.
- الأرقام بالأرقام (199 درهم). الآراء ديال الزبناء خليهم واقعيين وقصار، بأسامي ومدن مغربية.
- رجّع JSON فقط، بلا شرح وبلا ```."""


def write_landing(product_info, angle="", plan=None, photo=None):
    """Claude كيكتب المحتوى ديال صفحة الهبوط (Gemini كبديل إلا ماكانش مفتاح Claude)."""
    if MOCK:
        return {"title": "منتوج زوين كيحل ليك المشكل", "subtitle": "ساهل، سريع، وبثمن مناسب", "angle": angle or "الراحة",
                "price": "199 درهم", "old_price": "299 درهم", "cta": "اطلب دابا والخلاص عند الاستلام",
                "problem": "كل نهار كتعاني مع هاد المشكل.", "solution": "هاد المنتوج كيسهل عليك الحياة.",
                "benefits": [{"icon": "✅", "title": "جودة عالية", "text": "مواد متينة"},
                             {"icon": "🚚", "title": "توصيل سريع", "text": "24 حتى 48 ساعة"},
                             {"icon": "💵", "title": "الخلاص عند الاستلام", "text": "ماتخلص حتى توصلك"}],
                "how": ["اطلب", "كنتصلو بيك", "كتوصلك"],
                "social": [{"name": "فاطمة", "city": "الدار البيضاء", "text": "زوين بزاف، نصح بيه"}],
                "faq": [{"q": "شحال التوصيل؟", "a": "فابور فجميع المدن"}],
                "urgency": "الكمية محدودة", "guarantee": "ضمان الإرجاع 7 أيام",
                "image_prompts": ["product on a clean white studio background, soft light",
                                  "product being used at home, lifestyle, warm light",
                                  "close-up detail of the product texture",
                                  "product with its accessories laid out on a table"]}
    script = "\n".join(s["text"] for s in plan["segments"]) if plan and plan.get("segments") else ""
    user = f"""معلومات المنتوج: {product_info or "ماكاينش (شوف التصويرة)"}
زاوية البيع المطلوبة: {angle or "ختار أحسن زاوية نتا"}
{"التعليق ديال الفيديو الإعلاني (خلي الصفحة متناسقة معاه): " + script if script else ""}
{LANDING_SCHEMA}
زيد فالـ JSON حقل "image_prompts": 4 أوصاف بالإنجليزية لتصاور إعلانية ديال هاد المنتوج (نفس المنتوج بالضبط، بلا نص فالصورة):
1) hero: المنتوج بوحدو فستوديو نقي، 2) lifestyle: شخص مغربي كيستعملو فسياق حقيقي، 3) تفاصيل مقربة، 4) المنتوج مع المميزات/الإكسسوارات."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return _write_landing_gemini(product_info, angle, plan, photo)
    client = _claude_client()
    content = ([_image_block(photo)] if photo else []) + [{"type": "text", "text": user}]
    resp = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"), max_tokens=16000, system=LANDING_SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": "medium"},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude رفض يكتب هاد الصفحة")
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _parse_json(text)


def _write_landing_gemini(product_info, angle, plan, photo):
    from google.genai import types
    from PIL import Image
    client = _gemini_client()
    script = "\n".join(s["text"] for s in plan["segments"]) if plan and plan.get("segments") else ""
    prompt = f"""{LANDING_SYSTEM}
معلومات المنتوج: {product_info or "ماكاينش"}
زاوية البيع المطلوبة: {angle or "ختار أحسن زاوية نتا"}
{"التعليق ديال الفيديو: " + script if script else ""}
{LANDING_SCHEMA}
زيد حقل "image_prompts": 4 أوصاف بالإنجليزية لتصاور إعلانية ديال المنتوج (hero / lifestyle / close-up / accessories)."""
    contents = ([Image.open(photo)] if photo else []) + [prompt]
    resp = client.models.generate_content(model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"), contents=contents,
                                          config=types.GenerateContentConfig(response_mime_type="application/json",
                                                                             temperature=0.8))
    return _parse_json(resp.text)


IMAGE_STYLE = ("Professional e-commerce advertising photo, photorealistic, sharp, 4:5 vertical, "
               "keep the exact same product from the reference photo (same shape, colors, printed text, logo). "
               "No added text, no watermark, no extra products.")


def gen_product_images(photo: Path, prompts, out_dir: Path, max_n=4):
    """Nano Banana (Gemini Image): كيصاوب تصاور إعلانية من تصويرة المنتوج الحقيقية. كيرجع ليستة ديال الملفات."""
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    if MOCK:
        from PIL import Image, ImageDraw
        for i, pr in enumerate(prompts[:max_n], 1):
            im = Image.open(photo).convert("RGB").resize((864, 1080))
            ImageDraw.Draw(im).rectangle((0, 0, 864, 60), fill=(200, 200, 200))
            p = out_dir / f"ai_{i}.jpg"
            im.save(p, quality=85)
            made.append(p.name)
        return made
    from io import BytesIO
    from PIL import Image
    client = _gemini_client()
    ref = Image.open(photo).convert("RGB")
    ref.thumbnail((1024, 1024))
    for i, pr in enumerate(prompts[:max_n], 1):
        try:
            resp = client.models.generate_content(model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-lite-image"),
                                                  contents=[ref, f"{pr}. {IMAGE_STYLE}"])
            for part in resp.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    img = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
                    img.thumbnail((1200, 1500))
                    p = out_dir / f"ai_{i}.jpg"
                    img.save(p, quality=88)
                    made.append(p.name)
                    break
        except Exception as e:  # noqa — صورة وحدة فشلات ماتوقفش الباقي
            (out_dir / f"ai_{i}_error.txt").write_text(str(e)[:500])
    return made
