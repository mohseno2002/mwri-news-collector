#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""موجز اليوم — اختيار أهم قصص الرى من اللقطة المركزية وترتيبها بسلّم أهمية
م. محسن (١ قرار/تصريح الوزير · ٢ حدث ميدانى بالقاهرة والجيزة · ٣ ما يُقال عن
الوزارة إعلامياً · ٤ النيل والسد والفيضان).

قسمة العمل مقيسة (١٥/٩/٢٠٢٦): **الكود يفلتر ويعنقد، والنموذج يرتّب ويعلّل**.
تُرك الدمج للنموذج فى قياسين متتاليين فدمج «سفير أوزبكستان» مع «المبعوث
الفنلندى» فى واقعة واحدة وخرج سطر السبب يصف قصة غير عنوانها. بالعنقدة بالكود
اختفى الانزلاق تماماً.

والمرساة المصرية تُطبَّق قبل النداء لا داخله: النموذج لا يميّز وزير رى الجزائر
من وزير رى مصر حين لا يذكر العنوان البلد (مقيس: خمسة أخبار جزائرية مرّت رغم
أمر الاستبعاد الصريح فى التعليمة). الفلتر الصلب أسقطها ولم يُسقط خبراً مصرياً
واحداً من ٥٥ — بينما إسقاط «وزير الرى بلا دليل بلد» كان سيضيّع ١٣ خبراً مصرياً
حقيقياً، فلا يُسقط.
"""
import json, re, time, urllib.request
from datetime import datetime, timezone

GATEWAY = "https://mwri-ai.mohseno2002.workers.dev"
# فخّ مقيس ١٥/٩: حماية كلاودفلير تردّ 403 على هوية Python-urllib **قبل**
# الوصول للوركر — نفس الطلب بهوية متصفح يمرّ 200. الهوية إلزامية لا تجميل.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36 MWRI-NewsCollector/1.0"
WINDOW_H = 24          # نافذة الترشيح
MAX_CLUSTERS = 40      # ما يُرسل للنموذج
SHARE_WORDS = 4        # عتبة تشارك الكلمات للعنقدة ولمطابقة الأجنبى

# علامة أجنبية صريحة. السودان وإثيوبيا ليسا هنا عمداً — أخبار حوض النيل تخصّنا
# (نفس قاعدة التطبيق فى egyptAnchored).
FOREIGN = ["الأردن", "الاردن", "السعودية", "الرياض", "العراق", "بغداد", "سوريا", "دمشق",
           "اليمن", "صنعاء", "ليبيا", "الجزائر", "الجزائري", "الجزائرى", "تونس", "التونسي",
           "المغرب", "المغربي", "الكويت", "قطر", "الإمارات", "الامارات", "دبي", "أبوظبي",
           "ابوظبي", "البحرين", "لبنان", "بيروت", "تركيا", "إيران", "ايران",
           # مدن وألفاظ أضافها القياس الحى ١٥/٩: «الولايات الداخلية» و«بوزقزة»
           # جزائريتان، و«القنيطرة» عبرت لأن اسم البلد وحده لم يكفِ.
           "الولايات الداخلية", "بوزقزة", "وهران", "قسنطينة", "القنيطرة", "القنيطره",
           "طرابلس", "بنغازي", "مصراتة", "حلب", "إدلب", "ادلب", "الموصل", "البصرة",
           "إربد", "اربد", "الزرقاء", "مراكش", "الدار البيضاء"]

STOP = set("وزير وزارة اليوم صور بالصور فيديو عاجل التفاصيل مستندات خلال بعد قبل".split())


def clean_ar(v):
    t = re.sub(r"\s*-\s*[^-]{2,25}$", "", str(v or ""))
    t = re.sub(r"[^\u0600-\u06FF\s]", " ", t)
    return " ".join(t.split())


def words(t):
    return set(w for w in clean_ar(t).split() if len(w) > 3 and w not in STOP)


def is_foreign(text):
    return any(w in text for w in FOREIGN)


def row_ms(r):
    try:
        return datetime.fromisoformat(str(r.get("publishedAt", "")).replace("Z", "+00:00")).timestamp() * 1000
    except Exception:
        return r.get("seenAt") or 0


def candidates(rows, now_ms):
    """يرشّح نافذة الـ٢٤ ساعة، يُسقط الأجنبى الصريح ثم ما يشبهه (نفس الواقعة
    الأجنبية بعنوان لا يذكر البلد)، ثم يعنقد بتشارك الكلمات."""
    win = []
    for r in rows:
        age_h = (now_ms - row_ms(r)) / 3600000.0
        if -2 <= age_h <= WINDOW_H:
            win.append((r, age_h, clean_ar(r.get("title")) + " " + clean_ar(r.get("summary"))))
    win.sort(key=lambda x: x[1])
    blocked = [words(t) for _, _, t in win if is_foreign(t)]
    kept = []
    for r, age, t in win:
        if is_foreign(t):
            continue
        if any(len(words(t) & b) >= SHARE_WORDS for b in blocked):
            continue
        kept.append((r, age))
    clusters = []
    for r, age in kept:
        w = words(r.get("title"))
        for c in clusters:
            if len(w & c["w"]) >= SHARE_WORDS:
                c["n"] += 1
                c["w"] |= w
                if age < c["age"]:
                    c.update({"age": age, "row": r})
                break
        else:
            clusters.append({"row": r, "age": age, "n": 1, "w": w})
    clusters.sort(key=lambda c: (-c["n"], c["age"]))
    return clusters[:MAX_CLUSTERS], len(win), len(kept)


def ask(text, key, url=GATEWAY, timeout=90):
    req = urllib.request.Request(url, data=json.dumps({"task": "brief", "input": text}, ensure_ascii=False).encode("utf-8"),
                                 headers={"content-type": "application/json", "x-app-key": key, "user-agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def build(rows, now_ms, key, asker=None):
    """يرجع (brief, note). brief=None يعنى لا موجز هذه الجولة — والسبب فى note."""
    clusters, n_win, n_kept = candidates(rows, now_ms)
    if len(clusters) < 3:
        return None, "مرشحون قليلون (%d)" % len(clusters)
    lines = []
    for i, c in enumerate(clusters, 1):
        r = c["row"]
        lines.append("%d. %s [%s · منذ %.1fس · %d مصدر]" % (
            i, clean_ar(r.get("title"))[:150], str(r.get("sourceName") or "?"), c["age"], c["n"]))
    text = "العناوين مدمجة مسبقا ولا تكرار فيها — لا تدمج شيئا:\n" + "\n".join(lines)
    res = (asker or ask)(text, key)
    if not res or not res.get("ok"):
        return None, "البوابة: " + str((res or {}).get("code", "?"))
    stories = []
    for s in (res.get("data") or {}).get("stories") or []:
        try:
            i = int(s.get("i"))
        except Exception:
            continue
        if not (1 <= i <= len(clusters)):
            continue          # رقم مخترع — يُهمل ولا يُسقط الموجز
        c = clusters[i - 1]
        r = c["row"]
        try:
            cat = int(s.get("cat"))
        except Exception:
            cat = 0
        stories.append({"title": str(r.get("title") or "")[:190],
                        "url": r.get("url") or "",
                        "sourceName": r.get("sourceName") or "",
                        "publishedAt": r.get("publishedAt") or "",
                        "cat": cat if 1 <= cat <= 4 else 0,
                        "why": str(s.get("why") or "")[:160],
                        "sources": c["n"]})
    if not stories:
        return None, "الموجز رجع فارغاً"
    brief = {"at": int(now_ms), "n": len(stories), "stories": stories[:8],
             "by": res.get("by") or "ai", "pool": {"window": n_win, "kept": n_kept, "clusters": len(clusters)},
             "generatedAt": datetime.now(timezone.utc).isoformat()}
    return brief, "%d قصص من %d واقعة (%d خبراً فى النافذة)" % (len(brief["stories"]), len(clusters), n_win)
