#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مسبار قراءة فقط: هل يحتمل مخرج GitHub Actions مسحاً كاملاً لزوايا جوجل؟
لا يكتب فى Firebase ولا يمسّ الإنتاج. يُحذف بعد التقييم."""
import time, types, sys
src = open("collect_news.py", encoding="utf-8").read()
mod = types.ModuleType("c"); exec(src.split("def main()")[0], mod.__dict__)
feeds, _ = mod.load_feeds()
goog = [f for f in feeds if mod.feed_url(f["query"]).startswith("https://news.google.com/")]
direct = [f for f in feeds if f not in goog]
print("زوايا: %d (مباشرة %d + جوجل %d)" % (len(feeds), len(direct), len(goog)))

def sweep(label, fs):
    t0 = time.time()
    got = mod.fetch_all([mod.feed_url(f["query"]) for f in fs])
    ok = blocked = empty = 0; rows = []
    for f, g in zip(fs, got):
        if g and g.get("ok"):
            n = len(mod.parse_rss(g["body"], f))
            if n: ok += 1
            else: empty += 1
            rows.append((f["id"], "ok", n))
        else:
            why = (g or {}).get("why", "?")
            if "sorry" in str(why).lower() or "503" in str(why): blocked += 1
            rows.append((f["id"], why[:34], 0))
    el = time.time() - t0
    print("\n== %s: ناجحة %d · فارغة %d · محجوبة %d · من %d · %.1f ث"
          % (label, ok, empty, blocked, len(fs), el))
    for i, s, n in rows: print("   %-20s %-36s %4d" % (i, s, n))
    return ok, blocked, el

a_ok, a_bl, a_t = sweep("مسح كامل ١", goog)
print("\n--- هدنة ٦٠ ثانية ثم مسح كامل ثانٍ (اختبار الضغط) ---")
time.sleep(60)
b_ok, b_bl, b_t = sweep("مسح كامل ٢", goog)
print("\nالحكم: مسح١ %d/%d فى %.0f ث · مسح٢ %d/%d فى %.0f ث · محجوب %d"
      % (a_ok, len(goog), a_t, b_ok, len(goog), b_t, a_bl + b_bl))
