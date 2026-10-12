"""اختياري: forced alignment محلي بـ WhisperX (wav2vec2) باش يدقق توقيت كل كلمة اللي جابها Gemini.
مأخوذ من فكرة benmouad-ai/darija-word-captions. كيحتاج: pip install whisperx==3.8.6 (ثقيل: torch).
ماكيخدمش على السيرفر الصغير (2GB)؛ فعّلو بـ WHISPERX=1 غير على سيرفر قوي ولا GPU.
الكلمات ماكيتبدلوش أبدا، غير التوقيت. الكلمة اللي ماقدرش يحددها كتبقى بتوقيت Gemini."""
import re

LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
MODELS = {"ar": "jonatasgrosman/wav2vec2-large-xlsr-53-arabic", "fr": "jonatasgrosman/wav2vec2-large-xlsr-53-french",
          "en": None}  # en = الافتراضي ديال WhisperX
_cache = {}


def _model(lang, device):
    from whisperx.alignment import load_align_model
    if lang not in _cache:
        kw = {"model_name": MODELS[lang]} if MODELS.get(lang) else {}
        _cache[lang] = load_align_model(language_code=lang, device=device, **kw)
    return _cache[lang]


def refine(wav, words, pad=0.45, window=30.0):
    import torch
    from whisperx.alignment import align
    from whisperx.audio import load_audio
    device = "cuda" if torch.cuda.is_available() else "cpu"
    audio = load_audio(str(wav))
    # كنجمعو الكلمات فنوافذ ≤30 ثانية بنفس اللغة (عربي / لاتيني)
    groups, cur = [], []
    for w in words:
        lang = "en" if LATIN.search(w["w"]) else "ar"
        if cur and (lang != cur[-1][1] or w["s"] - cur[0][0]["s"] > window):
            groups.append(cur)
            cur = []
        cur.append((w, lang))
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        lang = g[0][1]
        start = max(0.0, g[0][0]["s"] - pad)
        end = min(len(audio) / 16000, g[-1][0]["e"] + pad)
        seg = [{"start": start, "end": end, "text": " ".join(w["w"] for w, _ in g)}]
        try:
            model, meta = _model(lang, device)
            res = align(seg, model, meta, audio, device, return_char_alignments=False)
            aligned = [w for s in res["segments"] for w in s.get("words", [])]
        except Exception:  # noqa
            aligned = []
        if len(aligned) != len(g):
            out.extend(w for w, _ in g)
            continue
        for (w, _), a in zip(g, aligned):
            if a.get("start") is not None and a.get("end") is not None and a["end"] > a["start"]:
                out.append({**w, "s": round(float(a["start"]), 2), "e": round(float(a["end"]), 2)})
            else:
                out.append(w)
    return sorted(out, key=lambda x: x["s"])
