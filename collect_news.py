#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مجمّع أخبار مرصد الري الذكي — يعمل على GitHub Actions (مستودع عام)
نفس منطق news-central 1.2 حرفياً: زوايا من sources-config.js المنشور، جلب من
جوجل نيوز بموجات ≤8، تنزيع XML بلا تصنيف، تفريد بالعنوان المطبَّع، سقف 40/زاوية
و600 إجمالاً، كتابة data/central/news فى Firebase بحارس hash، ونبضة /mwri/jobs.
لا أسرار: القاعدة تقبل الكتابة داخل /mwri بقواعدها الحالية.
"""
import hashlib, json, re, sys, time, urllib.parse, urllib.request, concurrent.futures as cf
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

RTDB = "https://ismailia-64500-default-rtdb.europe-west1.firebasedatabase.app"
NEWS_URL = RTDB + "/mwri/apps/irrigation-social-monitor/data/central/news.json"
JOB_URL = RTDB + "/mwri/jobs/news-central.json"
SOURCES_URL = "https://mohseno2002.github.io/irrigation-social-monitor/sources-config.js"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36 MWRI-NewsCollector/1.0"
NEWS_DAYS, NEWS_LIMIT, FEED_LIMIT, WAVE, WAVE_GAP, TIMEOUT, RETRIES = 7, 800, 40, 4, 1.5, 15, 2
# SLICE: عدد الزوايا لكل جولة. مقيس ٣/٩: جوجل تخنق بالحجم لا بالتباعد —
# ٢٩ زاوية × ٩٦ جولة = ~٢٨٠٠ طلب/يوم من مخرج واحد فيسقط المخرج كله
# (سقط Cloudflare دائماً وSupabase مؤقتاً، وسقطت الحاوية أمام عينى فى ٨٠ث).
# بالتناوب: ١٠/جولة كل ١٥ دقيقة ⇒ كل زاوية تُحدَّث كل ~٤٥ دقيقة، والحمل ×٢٫٩ أقل،
# والدمج فى اللقطة القائمة (موجود أصلاً) يبقيها كاملة داخل نافذة ٧ أيام.
SLICE = 10
SOFT_RETRY_PAUSE = 6.0
FEED_RE = re.compile(r'\{\s*id:\s*"([^"]+)",\s*name:\s*"([^"]+)",\s*query:\s*(?:\'([^\']*)\'|"([^"]*)")\s*\}')
GRP_RE = re.compile(r'\{\s*slug:\s*"([^"]+)",\s*nm:\s*"([^"]+)"')

def http(url, method="GET", body=None, headers=None, timeout=TIMEOUT):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    h = {"User-Agent": UA}; h.update(headers or {})
    if data is not None: h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")

def load_feeds():
    try:
        _, js = http(SOURCES_URL, timeout=15)
        feeds = [{"id": m[0], "name": m[1], "query": m[2] if m[2] else m[3]} for m in FEED_RE.findall(js)]
        for slug, nm in GRP_RE.findall(js):
            feeds.append({"id": "fbgrp_" + slug, "name": nm,
                          "query": '("مياه الري" OR "نقص مياه" OR "ترعة" OR "مصرف" OR "تطهير" OR "مزارعين") site:facebook.com/groups/' + slug})
        if len(feeds) >= 10: return feeds, "sources-config.js"
        raise RuntimeError("parsed %d" % len(feeds))
    except Exception as e:
        print("sources-config.js غير متاح:", e); sys.exit(2)

def clean(v): return re.sub(r"\s+", " ", str(v or "")).strip()
def decode(v):
    s = re.sub(r"<!\[CDATA\[([\s\S]*?)\]\]>", r"\1", str(v or ""))
    s = re.sub(r"&nbsp;", " ", s, flags=re.I); s = re.sub(r"&quot;", '"', s, flags=re.I)
    s = re.sub(r"&#0?39;|&apos;", "'", s, flags=re.I); s = re.sub(r"&lt;", "<", s, flags=re.I)
    s = re.sub(r"&gt;", ">", s, flags=re.I); s = re.sub(r"&amp;", "&", s, flags=re.I)
    return re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)
def strip(v): return clean(re.sub(r"<[^>]*>", " ", decode(v)))
def field(block, name):
    m = re.search(r"<" + name + r"(?:\s[^>]*)?>([\s\S]*?)</" + name + ">", block, re.I)
    return decode(m.group(1)) if m else ""
def feed_url(q):
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:%dd" % NEWS_DAYS, safe="") + "&hl=ar&gl=EG&ceid=EG:ar"

def parse_rss(xml, feed):
    out = []
    for part in re.split(r"<item>", xml, flags=re.I)[1:FEED_LIMIT + 1]:
        block = re.split(r"</item>", part, flags=re.I)[0]
        title = strip(field(block, "title")); url = clean(field(block, "link"))
        ext = clean(field(block, "guid")) or url or (feed["id"] + "|" + title)
        src = strip(field(block, "source")) or "موقع إخباري"
        summary = strip(field(block, "description"))
        if summary == title or summary.startswith(title + " "): summary = summary[len(title):].strip()
        try: pub = parsedate_to_datetime(clean(field(block, "pubDate")))
        except Exception: pub = datetime.now(timezone.utc)
        if not title: continue
        row = {"centralRaw": 1, "sourceName": src[:120], "title": title[:190], "summary": (summary or title)[:220],
               "url": url[:1200], "publishedAt": pub.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
               "feedId": feed["id"], "feedName": feed["name"]}
        if ext and ext != url: row["externalId"] = ext[:600]
        out.append(row)
    return out

def fetch_one(url):
    try:
        # CONSENT: جوجل تردّ بصفحة موافقة (أو موجز فارغ) على العناوين التى
        # تصنّفها سحابية/أوروبية ما لم يُرسَل الكوكى. فرضية قيد الاختبار ٣/٩.
        st, body = http(url, headers={"Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
                                      "Accept-Language": "ar-EG,ar;q=0.9",
                                      "Cookie": "CONSENT=YES+cb.20260903-00-p0.ar+FX+111"})
        if "<rss" not in body and "<feed" not in body: return {"ok": False, "why": "ليس RSS (صفحة اعتراض)"}
        # الخنق الناعم من جوجل: HTTP 200 بموجز RSS سليم وصفر <item>. كان يُحسب
        # نجاحاً فلا يدخل errors[] ولا تُعاد محاولته — وهو الفشل السائد فعلاً
        # (مقيس ٣/٩: ١٤/٢٩ زاوية «empty» بلا سبب واحد معلَن).
        if not re.search(r"<item[\s>]", body, re.I):
            # عيّنة من ردّ جوجل الحقيقى: الفرق بين «موجز سليم بصفر نتيجة»
            # و«صفحة موافقة/اعتراض» لا يُعرف من رمز الحالة. مقيس ٣/٩: نفس
            # الكود ١٠/١٠ من حاوية أنثروبيك و٠/١٠ من عامل GitHub.
            sample = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", body))[:120].strip()
            return {"ok": False, "why": "موجز فارغ · ردّ جوجل: " + (sample or "(فارغ تماماً)"), "soft": True}
        return {"ok": True, "body": body}
    except urllib.error.HTTPError as e: return {"ok": False, "why": "HTTP %d" % e.code}
    except Exception as e: return {"ok": False, "why": str(e)[:80]}

def fetch_all(urls):
    out = [None] * len(urls)
    def wave(idx):
        with cf.ThreadPoolExecutor(WAVE) as ex:
            for i, r in zip(idx, ex.map(lambda i: fetch_one(urls[i]), idx)): out[i] = r
        time.sleep(WAVE_GAP)
    idx = list(range(len(urls)))
    for s in range(0, len(idx), WAVE): wave(idx[s:s + WAVE])
    # الفشل الصلب (503/شبكة/مهلة) عابر ويُعاد. أما الخنق الناعم فالإلحاح عليه
    # يُعمّقه — مقيس ٣/٩: أربع جولات إلحاح خفضت المنتِج من ٥/١٢ إلى ٧/٢٩ —
    # فله محاولة واحدة بعد هدنة، ثم يُترك لجولة التناوب التالية.
    for attempt in range(1, RETRIES + 1):
        hard = [i for i in idx if not (out[i] and out[i]["ok"]) and not (out[i] or {}).get("soft")]
        if not hard: break
        time.sleep(3 * attempt)
        for s in range(0, len(hard), WAVE): wave(hard[s:s + WAVE])
    soft = [i for i in idx if not (out[i] and out[i]["ok"])]
    if soft:
        time.sleep(SOFT_RETRY_PAUSE)
        for s in range(0, len(soft), WAVE): wave(soft[s:s + WAVE])
    return out

def norm_title(v):
    s = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", clean(v)); s = re.sub(r"[أإآٱ]", "ا", s).replace("ى", "ي")
    return re.sub(r"[^\u0600-\u06FFA-Za-z0-9]+", " ", s).strip().lower()
def dedupe(rows):
    rows.sort(key=lambda r: r["publishedAt"], reverse=True)
    seen_u, seen_t, out = set(), set(), []
    for r in rows:
        tk = norm_title(r["title"])[:120]; uk = clean(r["url"])
        if (uk and uk in seen_u) or tk in seen_t: continue
        if uk: seen_u.add(uk)
        seen_t.add(tk); out.append(r)
        if len(out) >= NEWS_LIMIT: break
    return out
def content_hash(items):
    return hashlib.sha256(json.dumps([[i["url"], i["publishedAt"]] for i in items], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

def read_json(url, timeout=30):
    try: return json.loads(http(url, timeout=timeout)[1])
    except Exception: return None

def rotate(feeds, cursor):
    """شريحة الجولة بالتناوب الدائرى — الفهرس محفوظ فى عقدة المهمة لأن
       عامل Actions بلا حالة بين الجولات."""
    n = len(feeds)
    if n <= SLICE: return list(feeds), 0
    take = [feeds[(cursor + k) % n] for k in range(SLICE)]
    return take, (cursor + SLICE) % n

def merge_status(prev, results, now):
    """حالة الزوايا تراكمية: الشريحة الحالية تُحدَّث، وغيرها تحتفظ بآخر
       نتيجة معروفة مع عمرها — وإلا بدت ١٩ زاوية «فارغة» وهى لم تُسأل أصلاً."""
    by_id = {}
    for r in (prev or []):
        if isinstance(r, dict) and r.get("id"): by_id[r["id"]] = dict(r)
    for f, it, why in results:
        by_id[f["id"]] = {"id": f["id"], "name": f["name"], "count": len(it),
                          "state": "ok" if it else "empty", "at": now,
                          "why": ("" if it else (why or "بلا نتائج"))}
    for r in by_id.values():
        if r.get("at"): r["ageMin"] = int((now - r["at"]) / 60000)
    return list(by_id.values())

def main():
    started = time.time(); feeds, src = load_feeds()
    job = read_json(JOB_URL, timeout=20) or {}
    try: cursor = int(job.get("cursor") or 0)
    except Exception: cursor = 0
    take, next_cursor = rotate(feeds, cursor)
    got = fetch_all([feed_url(f["query"]) for f in take]); errors = []; results = []
    for f, g in zip(take, got):
        why = ""
        if g and g["ok"]:
            items = parse_rss(g["body"], f)
            if not items: why = "موجز بلا عناصر صالحة"
        else:
            items = []; why = (g or {}).get("why", "?")
            errors.append(f["name"] + ": " + why)
        results.append((f, items, why))
    ok_feeds = sum(1 for _, it, _ in results if it)
    empty = [f["name"] for f, it, _ in results if not it]
    fresh = dedupe([r for _, it, _ in results for r in it])
    now = int(time.time() * 1000)
    cur = read_json(NEWS_URL, timeout=30)
    prev_status = ((cur or {}).get("health") or {}).get("feedStatus") or []

    # الدمج هو الوضع الطبيعى الآن (الجولة تسأل شريحة لا كل الزوايا):
    # الجديد يغلب، والقديم يبقى داخل نافذة ٧ أيام.
    cutoff = (datetime.now(timezone.utc).timestamp() - NEWS_DAYS * 86400) * 1000
    old_items = []
    for r in ((cur or {}).get("items") or []):
        if not isinstance(r, dict) or not r.get("publishedAt"): continue
        try:
            if datetime.fromisoformat(r["publishedAt"].replace("Z", "+00:00")).timestamp() * 1000 >= cutoff:
                old_items.append(r)
        except Exception: continue
    merged = dedupe(fresh + old_items)
    status = merge_status(prev_status, results, now)
    live_ok = sum(1 for r in status if r.get("state") == "ok")
    health = {"state": "ok" if ok_feeds >= (len(take) + 1) // 2 and len(merged) >= 10 else "degraded",
              "successfulFeeds": live_ok, "totalFeeds": len(feeds),
              "sliceOk": ok_feeds, "sliceSize": len(take), "cursor": cursor,
              "failedFeeds": len(feeds) - live_ok,
              "emptyFeeds": len(empty), "emptyFeedNames": empty[:8],
              "feedStatus": status, "merged": True,
              "runMs": int((time.time() - started) * 1000), "errors": errors[:8], "feedsSrc": src}
    print("شريحة %d/%d (مؤشر %d→%d) · جديد %d · مدموج %d · %s · %.1fث"
          % (ok_feeds, len(take), cursor, next_cursor, len(fresh), len(merged), health["state"], time.time() - started))
    for e in errors[:6]: print("  ", e)

    h = content_hash(merged)
    stamp = {"at": now, "checkedAt": now, "generatedAt": datetime.now(timezone.utc).isoformat(),
             "by": "central-github", "producer": "github-actions", "health": health}
    if not fresh:
        # لا شىء جديد وصل: تُحدَّث checkedAt والحالة فقط، ويبقى at كما هو.
        # كتابة at جديداً هنا تجعل لقطةً قديمة تبدو «جُمعت الآن» فى التطبيق —
        # وهو الفشل الصامت نفسه فى ثوب الحداثة.
        http(NEWS_URL, "PATCH", {"checkedAt": now, "health": health,
                                 "lastError": (errors or ["لا عناصر جديدة"])[0]}, timeout=30)
        state = "kept(%d)" % len(merged)
    elif cur and cur.get("contentHash") == h and cur.get("items"):
        http(NEWS_URL, "PATCH", dict(stamp, count=len(merged)), timeout=30); state = "unchanged"
    else:
        http(NEWS_URL, "PUT", dict(stamp, schema=1, contentHash=h, count=len(merged),
                                   n=len(merged), items=merged), timeout=60)
        state = "stored(%d+%d→%d)" % (len(fresh), len(old_items), len(merged))

    # النجاح = الشريحة أنتجت. زاوية مخنوقة فى جولة تعود فى جولتها التالية.
    ok = ok_feeds > 0 and bool(merged)
    summary = "%s · شريحة %d/%d · زوايا حية %d/%d · عناصر %d · %.0fث" % (
        state, ok_feeds, len(take), live_ok, len(feeds), len(merged), time.time() - started)
    try:
        body = {"cursor": next_cursor, "last_run": {"at": int(time.time()), "by": "github-actions",
                                                    "summary": summary, "errors": errors[:6]}}
        if ok: body.update({"last_ok": int(time.time()), "last_err": None, "fail_streak": 0})
        else: body.update({"last_err": (errors or ["?"])[0][:200],
                           "fail_streak": int(job.get("fail_streak") or 0) + 1})
        http(JOB_URL, "PATCH", body, timeout=20)
    except Exception as e: print("heartbeat:", e)
    print("state:", state)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
