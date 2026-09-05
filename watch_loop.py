#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""حارس النبضة داخل جولة Actions واحدة — ٥/٩/٢٠٢٦

المشكلة المقيسة: جدولة GitHub (`*/5`) أطلقت ثلاث مرات فقط فى ١٢ ساعة
(٠١:٠١ · ٠٥:٤٨ · ١١:١٦ UTC) رغم أنها كل خمس دقائق؛ فطلب الزر اليدوى
(refreshReq) يظل معلّقاً ساعات ثم ينتهى عمره (٢٠ دقيقة) بلا خدمة، والدورة
المجدولة (٢٥ دقيقة) تصير ساعات. الجدولة عند GitHub «أفضل جهد» وتُسقَط تحت
الحِمل — وهى ليست ساعة يُعتمد عليها.

الحلّ بلا أى سرّ: الجولة الواحدة تبقى حيّة ~٢٥ دقيقة وتراقب عقدة المهمة
كل ٢٠ ثانية (ثلاث قراءات صغيرة، لا العقدة كلها)، فتستدعى collect_news.py
عند الاستحقاق (طلب يدوى أو مرور فاصل الدورة). وقبل انتهائها تطلق الجولة
التالية بـ`workflow_dispatch` عبر GITHUB_TOKEN المدمج (المستثنى من قاعدة
«ما يطلقه التوكن لا يشغّل ورك فلو» — الاستثناءان هما workflow_dispatch
وrepository_dispatch). الجدولة تبقى كمُعيد إشعال لو انقطعت السلسلة.
مجموعة concurrency تضمن جولة واحدة تعمل وأخرى واحدة بالانتظار على الأكثر.

الطلب اليدوى يُخدَم خلال ≤٢٠ ثانية + زمن الجمع (~٣٠ ث) بدل «حتى ٦ دقائق»
التى كانت وهماً.
"""
import os, subprocess, sys, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_news import should_run, JOB_URL, UA

RUN_SEC = int(os.environ.get("WATCH_RUN_SEC", "1500"))     # ٢٥ دقيقة
POLL_SEC = int(os.environ.get("WATCH_POLL_SEC", "20"))
DRY = os.environ.get("WATCH_DRY") == "1"
JOB_BASE = JOB_URL[:-len(".json")]

def leaf(key, timeout=15):
    req = urllib.request.Request(JOB_BASE + "/" + key + ".json", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "null")

def read_gate():
    """القراءات الثلاث الصغيرة التى تحتاجها should_run — لا العقدة كلها."""
    return {"last_ok": leaf("last_ok"), "refreshReq": leaf("refreshReq"), "refreshServedAt": leaf("refreshServedAt")}

def collect():
    if DRY:
        print("  (تجربة جافة — لم يُستدعَ المجمّع)"); return 0
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "collect_news.py")])
    return r.returncode

COOLDOWN_SEC = int(os.environ.get("WATCH_COOLDOWN_SEC", "300"))

def main():
    t0 = time.time(); deadline = t0 + RUN_SEC
    polls = 0; runs = 0; fails = 0
    # حارسان ضد الإلحاح على جوجل لو فشل الجمع قبل أن يكتب last_ok أو
    # refreshServedAt: (١) الطلب اليدوى الواحد يُحاوَل مرة واحدة فى الجولة؛
    # (٢) هدنة COOLDOWN بعد أى محاولة — فأسوأ حال ٥ محاولات فى ٢٥ دقيقة لا ٧٥.
    handled_req = 0; next_allowed = 0
    print("حارس النبضة: %d ثانية، نبضة كل %d ث" % (RUN_SEC, POLL_SEC))
    while time.time() < deadline:
        polls += 1
        try:
            job = read_gate()
            run, why, req_at = should_run(job)
        except Exception as e:
            run, why, req_at = False, "تعذّرت قراءة العقدة: " + str(e)[:120], None
        stamp = time.strftime("%H:%M:%S")
        if run and req_at and req_at == handled_req:
            run, why = False, "الطلب اليدوى حُوول فى هذه الجولة ولم يُسجَّل — لا إلحاح"
        if run and time.time() < next_allowed:
            run, why = False, "هدنة بعد المحاولة السابقة (%.0f ث)" % (next_allowed - time.time())
        if run:
            print("[%s] استحقاق: %s" % (stamp, why)); sys.stdout.flush()
            rc = collect(); runs += 1
            if rc != 0: fails += 1
            if req_at: handled_req = req_at
            next_allowed = time.time() + COOLDOWN_SEC
            print("[%s] المجمّع انتهى برمز %d" % (time.strftime("%H:%M:%S"), rc)); sys.stdout.flush()
            time.sleep(POLL_SEC)
            continue
        if polls % 15 == 1:
            print("[%s] %s" % (stamp, why)); sys.stdout.flush()
        time.sleep(POLL_SEC)
    print("انتهت الجولة: %d نبضة · %d جمع · %d فشل · %.0f ث" % (polls, runs, fails, time.time() - t0))
    # جولة الحارس ناجحة ما دام الحارس عمل؛ فشل جمع واحد يُقيَّد فى العقدة لا هنا
    sys.exit(0)

if __name__ == "__main__":
    main()
