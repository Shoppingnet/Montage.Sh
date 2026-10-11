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
  "ad": {"headline": "عنوان قصير وقوي للتصويرة (4 حتى 7 كلمات)", "price": "الثمن بالأرقام مثلا 199 درهم، ولا خاوي إلا ماكانش", "cta": "اطلب دابا", "badge": "الخلاص عند الاستلام"},
  "notes": "شرح قصير بالدارجة لشنو تبدل"
}
- جميع التوقيتات ديال segments و cuts و frames كتكون على التوقيت ديال الفيديو الأصلي (قبل القص والتسريع).
- frames: ختار اللحظات فين المنتوج باين كامل، كبير، واضح وماشي مضبب، وماكاينش شي حاجة مغطياه
  (ماشي لقطة فيها غير شخص كيستعمل المنتوج من بعيد، وماشي لقطة كحلة ولا فيها انتقال).
  ختار لقطات مختلفة (زوايا ولا ألوان مختلفة إلا كانت). box هو المربع اللي فيه المنتوج فداك اللقطة،
  بالأرقام من 0 حتى 1000 بهاد الترتيب: [ymin, xmin, ymax, xmax].
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
    ad = plan.get("ad") or {}
    plan["ad"] = {"headline": ad.get("headline") or plan["product"], "price": ad.get("price") or "",
                  "cta": ad.get("cta") or "اطلب دابا", "badge": ad.get("badge") or "الخلاص عند الاستلام"}
    return plan


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


def render_final(src: Path, plan, voice_id, work: Path, out: Path, subs=True, music: Path = None):
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
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"},
        json={"text": text, "model_id": os.getenv("ELEVEN_MODEL", "eleven_v4")},
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    out.write_bytes(r.content)


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
        placed.append({"file": clip, "start": start, "end": start + cd, "text": s["text"]})
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
    for p in placed:
        words = p["text"].split()
        if not words:
            continue
        chunks = [words[i:i + n] for i in range(0, len(words), n)]
        total_chars = sum(len(" ".join(c)) for c in chunks) or 1
        t = p["start"]
        dur = p["end"] - p["start"]
        for k, c in enumerate(chunks):
            d = dur * len(" ".join(c)) / total_chars
            style = "H" if k == 0 and p is placed[0] else "D"  # أول جملة (hook) بالأصفر
            txt = " ".join(c).replace("{", "(").replace("}", ")")
            lines.append(f"Dialogue: 0,{ts(t)},{ts(t + d)},{style},,0,0,0,,{txt}")
            t += d
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