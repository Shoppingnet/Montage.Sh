# API ديال Montage.Sh للموظفين الآليين (الوكلاء)

المفتاح: `API_TOKEN` فـ `.env` ديال السيرفر. كل طلب كيحمل `Authorization: Bearer <API_TOKEN>`.
الأساس: `http://<IP>:8000`

## 1) صيفط فيديو(هات)
`POST /submit` (multipart):
- `videos` (ملف، يقدر يتكرر) **ولا** `links_text` (روابط Drive/YouTube، واحد فكل سطر)
- `product_info` (معلومات المنتوج)، `instruction` (أمر بالدارجة، اختياري)
- `voice` (voice_id ديال ElevenLabs، اختياري — الافتراضي MASTER ADS VOICE)
- `auto_approve=1` باش يتصاوب الصوت والمونتاج بلا مراجعة
- الخيارات: `opt_subs=1` ترجمة، `opt_clean=1` مسح الكتابة الأجنبية، `opt_sizes=1` 3 مقاسات، `opt_ab=1` نسخ A/B، `opt_music=<file|auto|none>`، `mode=dub|captions`، `make_images=1` تصاور الإعلانات، `product_photo_file` تصويرة المنتوج
- الجواب: `{"batch": "...", "jobs": ["id1", ...], "errors": []}`

## 2) تبع الحالة
`GET /api/job/{id}` → `status` (`queued, analyzing, review, approved, rendering, done, error`)، `step`، `plan` (السكريبت)، `files` (روابط التحميل).

## 3) قبل (إلا ما درتيش auto_approve)
`POST /api/job/{id}/approve`. باش تبدل السكريبت قبل القبول: `POST /job/{id}/save` بنفس الحقول ديال الفورم (`seg_start[]`, `seg_end[]`, `seg_text[]`, `action=approve`).

## 4) حمّل
`GET /files/{id}/final.mp4` (و `final.srt`, `final_b.mp4`, `final_9x16.mp4`, `ads.zip`...).

## مثال (bash)
```bash
T=$API_TOKEN; B=http://IP:8000
R=$(curl -s -H "Authorization: Bearer $T" -F videos=@clip.mp4 -F "product_info=كرسي مريح 199 درهم" -F auto_approve=1 -F opt_clean=1 $B/submit)
ID=$(echo "$R" | python3 -c 'import json,sys;print(json.load(sys.stdin)["jobs"][0])')
until [ "$(curl -s -H "Authorization: Bearer $T" $B/api/job/$ID | python3 -c 'import json,sys;print(json.load(sys.stdin)["status"])')" = done ]; do sleep 15; done
curl -s -H "Authorization: Bearer $T" -o final.mp4 $B/files/$ID/final.mp4
```
