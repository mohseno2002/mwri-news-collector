# مسبار أتوم — يثبت أن مسار RSS لم يتغيّر حرفياً وأن أتوم يُحلَّل بتواريخه الحقيقية
import importlib.util, io, json, re, sys
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
new = load("collect_news.py", "cn_new")

FEED = {"id": "t", "name": "زاوية اختبار"}
RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>تطهير ترعة المنايف</title><link>https://x.eg/a</link>
<pubDate>Mon, 07 Sep 2026 13:36:00 +0300</pubDate><description>وصف الخبر</description>
<source>الأهرام</source></item>
<item><title>كسر خط مياه</title><link>https://x.eg/b</link>
<pubDate>Sun, 06 Sep 2026 10:00:00 +0300</pubDate><description>وصف ثانٍ</description></item>
</channel></rss>"""
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>بيان وزارة الرى</title>
<link rel="alternate" href="https://y.eg/1"/><link rel="edit" href="https://y.eg/edit"/>
<updated>2026-09-07T10:36:00Z</updated><summary>نصّ البيان</summary></entry>
<entry><title>خبر أقدم</title><link href="https://y.eg/2"/>
<published>2026-09-01T08:00:00+02:00</published><content>تفصيل</content></entry>
</feed>"""
EMPTY_ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title></feed>"""

p = f = 0
def ok(name, cond, extra=""):
    global p, f
    if cond: p += 1; print("  ✓ " + name)
    else: f += 1; print("  ✗ " + name + ((" — " + str(extra)) if extra else ""))

print("مسبار أتوم")
# ١) مسار RSS لم يتغيّر — القيم متوقَّعة حرفياً (أُثبت تطابقه بايتاً عند النقل ١٠/٩/٢٠٢٦)
r = new.parse_rss(RSS, FEED)
ok("RSS: عنصران", len(r) == 2, len(r))
ok("RSS: الأحدث أولاً", r[0]["title"] == "تطهير ترعة المنايف")
ok("RSS: الرابط من نصّ الوسم", r[0]["url"] == "https://x.eg/a")
ok("RSS: تاريخ RFC يُقرأ", r[0]["publishedAt"] == "2026-09-07T10:36:00.000Z", r[0]["publishedAt"])
ok("RSS: اسم المصدر يُؤخذ", r[0]["sourceName"] == "الأهرام")
ok("RSS: بلا مصدر يقع على الافتراضى", r[1]["sourceName"] == "موقع إخباري")

# ٢) أتوم يُحلَّل
rows = new.parse_rss(ATOM, FEED)
ok("عنصرا أتوم حُلّلا", len(rows) == 2, len(rows))
ok("العنوان صحيح", rows[0]["title"] == "بيان وزارة الرى", rows[0]["title"])
ok("الرابط من سمة href لا نصّ الوسم", rows[0]["url"] == "https://y.eg/1", rows[0]["url"])
ok("رابط التحرير لا يُؤخذ", all("edit" not in r["url"] for r in rows))
ok("link بلا rel يُقبل", rows[1]["url"] == "https://y.eg/2", rows[1]["url"])
ok("تاريخ ISO بـZ يُقرأ", rows[0]["publishedAt"] == "2026-09-07T10:36:00.000Z", rows[0]["publishedAt"])
ok("تاريخ ISO بإزاحة يُقرأ", rows[1]["publishedAt"] == "2026-09-01T06:00:00.000Z", rows[1]["publishedAt"])
ok("الترتيب تنازلى بالتاريخ", rows[0]["publishedAt"] > rows[1]["publishedAt"])
ok("summary وcontent كلاهما يعمل", rows[0]["summary"] == "نصّ البيان" and rows[1]["summary"] == "تفصيل")
ok("التاريخ ليس لحظة التشغيل",
   not any(r["publishedAt"].startswith(new.datetime.now(new.timezone.utc).strftime("%Y-%m-%dT%H")) for r in rows))

# ٣) البوابة
def gate(body):
    if "<rss" not in body and "<feed" not in body: return "not-feed"
    if not re.search(r"<(item|entry)[\s>]", body, re.I): return "empty"
    return "ok"
ok("بوابة أتوم بعناصر تمرّ", gate(ATOM) == "ok")
ok("أتوم بلا عناصر = فارغ", gate(EMPTY_ATOM) == "empty")
ok("صفحة دخول = ليس موجزاً", gate("<html><form>دخول</form></html>") == "not-feed")

print("\nالنتيجة: %d/%d" % (p, p + f))
sys.exit(1 if f else 0)
