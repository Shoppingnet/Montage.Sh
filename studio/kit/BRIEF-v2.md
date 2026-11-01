# BRIEF v2 — رجوع للطريقة اللي نجحات (01/11/2026, Top)
Top rejected the latest batch: scripts tired/weak, too short (one is 20 s), voice not matching the motion, weak selling angles, male voice makes mistakes. The method had drifted from the one that produced the winners. Follow THIS, which restores it. Source of truth: project docs claude/winning-videos-analysis.md, claude/montage-rules-CLAUDE.md, claude/hooks-list-top.md (copies summarized here).

## 1. Voice
- FEMALE ONLY: Gemini `gemini-3.8-flash-tts`, voice **Laomedeia**. NO male voice (Charon makes mistakes). Use only the 20 woman hooks.
- Energetic, excited sales voice that pushes to buy; natural Moroccan, never robotic.

## 2. Length
- **30–45 s** of voice (never under 30). If footage is short: slow motion down to ~0.55×, never repeat the same seconds.

## 3. SHOTS FIRST, then script (this is what makes voice = motion)
1. Watch EVERY clip (contact sheets at 0.5–1 s steps). Write a shot list: clip, start–end, what is visibly happening (action, not just "the product").
2. Order the shots as a selling story: PROBLEM (first 1–3 s, the customer's pain WITHOUT the product, visible) → product appears → product WORKING (motion, before/after, result in 3–5 s) → each selling angle with the shot that proves it → end.
3. Write ONE short sentence per shot that says exactly what that shot shows while it shows it. Never describe something that isn't on screen at that moment. No sentence without its shot, no shot without its sentence.
4. Then voice, then Whisper word times, then cut each shot exactly at its sentence's start/end words.

## 4. Hook
- Pick from Top's 20 woman hooks (hooks-list-top.md), matched to the product's problem, and vary them across products: problem products → 6 «حَبْسي شوية! عندك هاد المشكل حتى نتي؟» / 8 «واش باقي كتديري هادشي بالطريقة القديمة؟»; visible transformation → 12 «شوفي الفرق! قبل ودابا!» (ONLY if the footage shows before/after); surprising function → 10 «ما غاديش تصدقي آش كيدير هادا!»; home/family → 13 «لا لا! هادي خاصها تكون فكل دار!»; etc. Hook 1–3 s, then immediately the problem.

## 5. Selling angles (cover most of them, each with its proving shot)
problem it solves · how easy/fast · result (clean/organized/comfortable) · saves time/space/money · quality/solidity (only if visible) · who it's for (family, kids, kitchen, car) · portability/folding/storage · gift. No invented claims (no price unless certain, no free delivery, no guarantees, no specs not visible).

## 6. Language
- Darija only: /home/claude/kit/darija-dictionary.md (Fusha→Darija) + /home/claude/pronunciation-dictionary.md (Top's own corrections win, copy character by character). Gloves = «الليگات». Heating = «كَيْسَخّْنْ» (never سخانة/الشوفاج for a product's heat). French loanwords P=پ V=ڤ G=گ. Full tashkeel on every word.
- Ending: the female ending in pronunciation-dictionary.md §5 exactly (with «الْمُدُنْ»), CTA «دُوزِي الْكُومُونْدْ دْيَالْكْ دَابَا!».

## 7. Montage
- Kit: /home/claude/kit (tts.py, wt.py, build.py; /home/claude/tools/build2.py adds |slow). FRAME_STYLE = the same frame the product already has (keep it).
- No burned-in text/watermarks/foreign captions (crop band or skip), no over-zoom, no repeated or near-identical shots, exact product only, sharp shots only.
- Review final_sheet.jpg; check that each sentence's shot really shows it.

## 8. Lessons from the 01/11 redo (apply every time)
- Voice: generate 3 takes, keep the best by Whisper match; trim long pauses to ~0.28 s. Every number/price spoken must be checked by Whisper (e.g. 199 must not come out as 109).
- No claim that the footage doesn't show (e.g. "goes in the washing machine", "better than ordinary ones"). If no shot proves it, drop the sentence.
- Price only if it is in the product name (Top's file); say it in words.
- Crop out watermarks / creator faces / burned captions (band crop); skip AI-fantasy or other-product clips.
- Build tools: /home/claude/mytools/build3.py (|s1.7 slow, |x0.82 side crop) or /home/claude/toolsB/buildB.py (+ timeplan.py, tighten.py, bw.sh waits for running ffmpeg). Never run two encodes at once (2 CPUs).
- Footage download: /home/claude/dl.py REF (reads work/REF/urls.json; TikTok + direct mp4 work, YouTube/Douyin don't). Source list for each product: /home/claude/ready.json.
- Report per product: file, duration, hook #, script, shot per sentence, weak points, new Darija words to confirm.
- (02/11) Gemini sometimes drops vowels: «السَّفَرْ» came out «السْفْرْ» (SN9080). Words in the pronunciation dictionary with explicit fatha must be re-checked after TTS; if a take drops them, re-voice that line.
- (02/11) Never build a whole video from one low-res clip (e.g. 360x640) with band crop + upscale: result is blurry everywhere (SN8056). Check source resolution first; prefer ≥720p sources; extract full-res frames and look at sharpness before delivering. No filler shots (blank fridge door, sink) that don't show the product.
