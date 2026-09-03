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
NEWS_DAYS, NEWS_LIMIT, FEED_LIMIT, WAVE, WAVE_GAP, TIMEOUT, RETRIES = 7, 600, 40, 4, 1.0, 15, 3
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
        st, body = http(url, headers={"Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5", "Accept-Language": "ar-EG,ar;q=0.9"})
        if "<rss" not in body and "<feed" not in body: return {"ok": False, "why": "not RSS"}
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
    # جوجل ترمى 503 على دفعات عابرة: إعادة حتى 3 مرات بتباعد 3/6/9 ثوانٍ
    for attempt in range(1, RETRIES + 1):
        failed = [i for i in idx if not (out[i] and out[i]["ok"])]
        if not failed: break
        time.sleep(3 * attempt)
        for s in range(0, len(failed), WAVE): wave(failed[s:s + WAVE])
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

def main():
    started = time.time(); feeds, src = load_feeds()
    got = fetch_all([feed_url(f["query"]) for f in feeds]); errors = []; results = []
    for f, g in zip(feeds, got):
        if g and g["ok"]: results.append((f, parse_rss(g["body"], f)))
        else: errors.append(f["name"] + ": " + (g or {}).get("why", "?")); results.append((f, []))
    ok_feeds = sum(1 for _, it in results if it); empty = [f["name"] for f, it in results if not it]
    items = dedupe([r for _, it in results for r in it]); h = content_hash(items); now = int(time.time() * 1000)
    health = {"state": "ok" if ok_feeds >= (len(feeds) + 1) // 2 and len(items) >= 10 else "degraded",
              "successfulFeeds": ok_feeds, "totalFeeds": len(feeds), "failedFeeds": len(feeds) - ok_feeds,
              "emptyFeeds": len(empty), "emptyFeedNames": empty[:8],
              "feedStatus": [{"id": f["id"], "name": f["name"], "count": len(it), "state": "ok" if it else "empty"} for f, it in results],
              "runMs": int((time.time() - started) * 1000), "errors": errors[:8], "feedsSrc": src}
    print("feeds %d/%d · items %d · %s · %.1fs" % (ok_feeds, len(feeds), len(items), health["state"], time.time() - started))
    for e in errors[:5]: print("  ", e)
    try: cur = json.loads(http(NEWS_URL, timeout=30)[1])
    except Exception: cur = None
    if health["state"] != "ok" and cur and cur.get("items"):
        http(NEWS_URL, "PATCH", {"checkedAt": now, "health": health, "lastError": (errors or ["نتائج أقل من الحد الآمن"])[0]}, timeout=30)
        state = "kept"
    else:
        stamp = {"at": now, "checkedAt": now, "generatedAt": datetime.now(timezone.utc).isoformat(), "by": "central-github", "producer": "github-actions", "health": health}
        if cur and cur.get("contentHash") == h and cur.get("items"):
            http(NEWS_URL, "PATCH", dict(stamp, count=len(cur["items"])), timeout=30); state = "unchanged"
        else:
            http(NEWS_URL, "PUT", dict(stamp, schema=1, contentHash=h, count=len(items), n=len(items), items=items), timeout=60); state = "stored"
    ok = health["state"] == "ok" or state == "kept"
    try:
        curj = json.loads(http(JOB_URL, timeout=20)[1]) or {}
        body = {"last_ok": int(time.time()), "last_err": None, "fail_streak": 0} if ok else {"last_err": (errors or ["?"])[0][:200], "fail_streak": int(curj.get("fail_streak") or 0) + 1}
        http(JOB_URL, "PATCH", body, timeout=20)
    except Exception as e: print("heartbeat:", e)
    print("state:", state)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
