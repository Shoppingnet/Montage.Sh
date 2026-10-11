"""تصاور الإعلانات بجميع المقاسات (Meta / Google Demand Gen / YouTube) من أحسن لقطات الفيديو."""
import os
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

FONT = Path(__file__).parent / "fonts" / "Cairo.ttf"
RAQM = features.check("raqm")

# الأماكن الإعلانية والمقاسات ديالها
PLACEMENTS = {
    "meta_feed_1x1": (1080, 1080, "Meta — فيد مربع"),
    "meta_feed_4x5": (1080, 1350, "Meta — فيد طولاني"),
    "story_reels_9x16": (1080, 1920, "Stories / Reels / Shorts"),
    "google_landscape": (1200, 628, "Google Demand Gen — عرضي 1.91:1"),
    "google_square": (1200, 1200, "Google Demand Gen — مربع"),
    "google_portrait": (960, 1200, "Google Demand Gen — طولاني 4:5"),
    "youtube_thumb": (1280, 720, "YouTube — 16:9"),
}

BRAND = os.getenv("AD_COLOR", "#E4572E")


def _font(size, weight="Bold"):
    f = ImageFont.truetype(str(FONT), size, layout_engine=ImageFont.Layout.RAQM if RAQM else ImageFont.Layout.BASIC)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def _shape(text):
    """إلا ماكانش raqm، كنشكلو الحروف العربية يدويا."""
    if RAQM:
        return text
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text))


def _text_w(draw, text, font):
    l, t, r, b = draw.textbbox((0, 0), _shape(text), font=font, direction="rtl" if RAQM else None)
    return r - l, b - t


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if _text_w(draw, test, font)[0] <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_rtl(draw, xy_right, text, font, fill):
    x_right, y = xy_right
    w, _ = _text_w(draw, text, font)
    kw = {"direction": "rtl"} if RAQM else {}
    draw.text((x_right - w, y), _shape(text), font=font, fill=fill, **kw)


def best_frames(video, count=2):
    """كيختار أوضح لقطات من أجزاء مختلفة ديال الفيديو."""
    import cv2
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    cands = []
    for i in range(24):
        idx = int(total * (0.05 + 0.9 * i / 23))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
        bright = gray.mean()
        penalty = 0.3 if bright < 40 or bright > 225 else 1.0
        cands.append((sharp * penalty, i, frame))
    cap.release()
    # نقسمو الفيديو على count أجزاء وناخدو الأحسن فكل جزء
    picked = []
    for k in range(count):
        part = [c for c in cands if k * 24 / count <= c[1] < (k + 1) * 24 / count]
        if part:
            best = max(part, key=lambda c: c[0])
            picked.append(Image.fromarray(cv2.cvtColor(best[2], cv2.COLOR_BGR2RGB)))
    return picked


def frames_at(video, frames):
    """كياخد اللقطات فالتوقيتات اللي ختار Gemini (أوضح وحدة فـ ±0.4 ثانية)، وكيقطع على المنتوج."""
    import cv2
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    picked = []
    for fr in frames:
        best = None
        for dt in (-0.4, -0.2, 0, 0.2, 0.4):
            idx = min(total - 1, max(0, int((fr["t"] + dt) * fps)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharp = cv2.Laplacian(gray, cv2.CV_64F).var() * (0.3 if gray.mean() < 40 else 1.0)
            if best is None or sharp > best[0]:
                best = (sharp, frame)
        if best is None:
            continue
        img = Image.fromarray(cv2.cvtColor(best[1], cv2.COLOR_BGR2RGB))
        picked.append(crop_product(img, fr.get("box")))
    cap.release()
    return picked


def crop_product(img: Image.Image, box):
    """كيقطع على المنتوج مع هامش، باش يبان كبير فالتصويرة."""
    if not box:
        return img
    W, H = img.size
    y0, x0, y1, x1 = box[0] * H / 1000, box[1] * W / 1000, box[2] * H / 1000, box[3] * W / 1000
    bw, bh = x1 - x0, y1 - y0
    m = 0.18 * max(bw, bh)
    # ماكنقطعوش صغير بزاف باش ماتولّيش الصورة مضببة
    side_w, side_h = max(bw + 2 * m, W * 0.3), max(bh + 2 * m, H * 0.3)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    l, t = max(0, cx - side_w / 2), max(0, cy - side_h / 2)
    r, b = min(W, l + side_w), min(H, t + side_h)
    l, t = max(0, r - side_w), max(0, b - side_h)
    return img.crop((int(l), int(t), int(r), int(b)))


def ai_polish(frame: Image.Image, product, out_dir: Path, idx):
    """اختياري: Gemini Image كيحسن اللقطة لصورة منتوج احترافية. إلا فشل كنرجعو اللقطة الأصلية."""
    if os.getenv("AD_AI_POLISH", "0") != "1" or os.getenv("MOCK") == "1":
        return frame
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = (f"Turn this video frame of the product '{product}' into a clean, bright, professional "
                  "e-commerce advertising photo. Keep the exact same product, shape, colors and any printed "
                  "text unchanged. Improve lighting and sharpness, simple tasteful background. No added text.")
        resp = client.models.generate_content(model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-lite-image"),
                                              contents=[frame, prompt])
        for part in resp.candidates[0].content.parts:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                from io import BytesIO
                img = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
                img.save(out_dir / f"polished_{idx}.jpg", quality=92)
                return img
    except Exception as e:  # noqa
        (out_dir / f"polish_error_{idx}.txt").write_text(str(e))
    return frame


def compose(frame: Image.Image, size, ad):
    W, H = size
    canvas = Image.new("RGB", (W, H))
    # الخلفية: نفس اللقطة مكبرة ومضببة
    bg = frame.copy()
    s = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1)).filter(ImageFilter.GaussianBlur(28))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    canvas.paste(Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.25))
    d = ImageDraw.Draw(canvas, "RGBA")

    headline = (ad.get("headline") or "").strip()
    price = (ad.get("price") or "").strip()
    cta = (ad.get("cta") or "اطلب دابا").strip()
    cod = (ad.get("badge") or "الخلاص عند الاستلام").strip()

    landscape = W / H > 1.3
    unit = H * 0.95 if landscape else min(W, H * 0.85)
    pad = int(unit * 0.05)
    if landscape:
        tx0, tx1 = int(W * 0.56), W - pad
    else:
        tx0, tx1 = pad, W - pad
    max_w = tx1 - tx0

    # نقيسو البلوك ديال النص قبل ما نرسمو
    hf = _font(int(unit * 0.075), "Bold")
    sf = _font(int(unit * 0.040), "SemiBold")
    pf = _font(int(unit * 0.065), "Black")
    cf = _font(int(unit * 0.050), "Bold")
    lines = _wrap(d, headline, hf, max_w)[:2] if headline else []
    lh = int(hf.size * 1.4)
    row_h = int(unit * 0.11)
    block_h = len(lines) * lh + int(sf.size * 1.8) + row_h

    if landscape:
        ty = (H - block_h) // 2
        area = (pad, pad, int(W * 0.52), H - pad)
    else:
        safe = int(H * 0.13) if H / W > 1.6 else 0  # Stories/Reels: الواجهة كتغطي التحت
        band_h = block_h + 2 * pad + safe
        d.rectangle((0, H - band_h, W, H), fill=(10, 10, 12, 220))
        ty = H - band_h + pad
        area = (pad, pad, W - pad, H - band_h - pad)

    # المنتوج
    aw, ah = area[2] - area[0], area[3] - area[1]
    fs = min(aw / frame.width, ah / frame.height)
    fg = frame.resize((max(1, int(frame.width * fs)), max(1, int(frame.height * fs))), Image.LANCZOS)
    rad = int(min(fg.size) * 0.05)
    mask = Image.new("L", fg.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *fg.size), radius=rad, fill=255)
    px, py = area[0] + (aw - fg.width) // 2, area[1] + (ah - fg.height) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((px + 10, py + 14, px + fg.width + 10, py + fg.height + 14),
                                             radius=rad, fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.paste(shadow, (0, 0), shadow)
    canvas.paste(fg, (px, py), mask)
    d = ImageDraw.Draw(canvas, "RGBA")

    # النص
    for line in lines:
        _draw_rtl(d, (tx1, ty), line, hf, "white")
        ty += lh
    _draw_rtl(d, (tx1, ty), cod, sf, (225, 225, 225))
    ty += int(sf.size * 1.8)

    right = tx1
    if price:
        pw, _ = _text_w(d, price, pf)
        box = (tx1 - pw - int(unit * 0.07), ty, tx1, ty + row_h)
        d.rounded_rectangle(box, radius=int(row_h * 0.25), fill="#FFD23F")
        _draw_rtl(d, (box[2] - int(unit * 0.035), ty + (row_h - pf.size * 1.45) / 2), price, pf, (20, 20, 20))
        right = box[0] - int(unit * 0.03)
    cw, _ = _text_w(d, cta, cf)
    cbox = (right - cw - int(unit * 0.09), ty, right, ty + row_h)
    if cbox[0] >= tx0 - 2:
        d.rounded_rectangle(cbox, radius=int(row_h * 0.5), fill=BRAND)
        _draw_rtl(d, (cbox[2] - int(unit * 0.045), ty + (row_h - cf.size * 1.45) / 2), cta, cf, "white")
    return canvas


def make_ad_images(video: Path, ad: dict, out_dir: Path, product="", picks=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = frames_at(video, picks) if picks else []
    if not frames:
        frames = best_frames(video, int(os.getenv("AD_FRAMES", "2")))
    files = []
    for i, fr in enumerate(frames, 1):
        fr = ai_polish(fr, product or ad.get("headline", ""), out_dir, i)
        for key, (w, h, _) in PLACEMENTS.items():
            img = compose(fr, (w, h), ad)
            p = out_dir / f"v{i}_{key}_{w}x{h}.jpg"
            img.save(p, quality=90)
            files.append(p)
    z = out_dir / "ads.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.name)
    return files, z
