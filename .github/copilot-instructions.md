# تعليمات Copilot — مستودع mwri-news-collector

## ما هذا المستودع
مجمّع أخبار «مرصد الري الذكي» لوزارة الموارد المائية والري (م. محسن الشامى). سكربت واحد
`collect_news.py` يعمل على GitHub Actions (`.github/workflows/collect.yml`) كل ١٥ دقيقة:
يقرأ الزوايا من `https://mohseno2002.github.io/irrigation-social-monitor/sources-config.js`
(مصدر الحقيقة الوحيد — لا تُنسخ الزوايا هنا)، يجلب Google News RSS، ينزّع ويفرّد ويدمج،
ويكتب اللقطة فى Firebase `mwri/apps/irrigation-social-monitor/data/central/news`
مع نبضة فى `mwri/jobs/news-central`.

## كيف تتحقق أن آخر تشغيل نجح (بلا فتح السجلات)
اقرأ `https://ismailia-64500-default-rtdb.europe-west1.firebasedatabase.app/mwri/jobs/news-central.json`:
`last_run.summary` مثل `stored · feeds 27/29 · items 512 · ok · 18s`. الحالات:
- `stored` / `unchanged` = نجاح كامل.
- `merged(a+b→c)` = جولة ناقصة دُمجت فى اللقطة (طبيعى تحت حدّ جوجل).
- `kept` = لم يُجلب شىء جديد؛ لو تكررت ٤ مرات متتالية فجوجل تحدّ مخرج GitHub — لا تزد الجدولة.

## قواعد لا تُخالَف
1. **لا تزد وتيرة الجدولة عن `*/15`** ولا التزامن `WAVE` عن ٤ ولا تحذف التباعد — جوجل تحجب
   بصفحة Sorry/503 أو تُرجع 200 بلا عناصر عند الإفراط، والحجب يستمر ساعات ويصيب كل المخارج.
2. **لا تُعدّل الزوايا هنا** — تُعدَّل فى `sources-config.js` بمستودع التطبيق فقط.
3. **لا تُضف مكتبات** — بايثون قياسى فقط (يعمل بلا تثبيت).
4. **لا أسرار** فى هذا المستودع (عام عمداً لدقائق Actions المجانية)؛ لا تضف مفاتيح ولا توكنات.
5. أى تغيير فى المنطق يُحافظ على مخطط اللقطة (الحقول: at · checkedAt · by · producer · health ·
   contentHash · count · n · items[…]) لأن تطبيق المرصد يقرؤه كما هو.
6. الجولة الناقصة تُدمج ولا تُهمَل، والفشل الكامل يُنهى التشغيل أحمر (exit 1).

## عند الطلب «شغّل الورك فلو»
افتح `.github/workflows/collect.yml` ← Run workflow (workflow_dispatch مفعَّل)، ثم اقرأ
`last_run.summary` من الرابط أعلاه بعد دقيقة وأبلغ النتيجة بالأرقام.
