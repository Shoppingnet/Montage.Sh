# Montage.Sh — نظام الدبلجة بالدارجة (Shopping Net)

- المستعمل كيهضر بالدارجة المغربية (حروف عربية). جاوب بالدارجة.
- الواجهة كاملة بالدارجة و RTL، ومصاوبة للتلفون.
- الملفات: `pipeline.py` (المعالجة: تحميل، وضوح، Gemini، TTS، مونتاج FFmpeg)، `ad_images.py` (تصاور الإعلانات)، `app.py` (FastAPI + الخدامة فالخلفية + SQLite)، `templates/`.
- الاختيارات المقررة: السكريبت بـ Gemini (ديريكت، ماشي OpenRouter)، الصوت ElevenLabs (الافتراضي MASTER ADS VOICE) و Gemini TTS كبديل رخيص.
- التجربة بلا مفاتيح: `MOCK=1 uvicorn app:app`. ديما جرب بـ MOCK قبل ما تقول خدام.
- ماتحطش المفاتيح فالكود ولا فالـ commits. كيبقاو غير فـ `.env` فالسيرفر.
- التثبيت: `deploy/setup.sh` على Ubuntu (DigitalOcean)، الخدمة `darija-dubbing` فالبور 8000.
