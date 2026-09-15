# -*- coding: utf-8 -*-
"""مسبار موجز اليوم — بلا شبكة (الاستدعاء مزيَّف)."""
import json, daily_brief as B
p=f=0
def ok(n,c):
    global p,f
    if c: p+=1; print("✔",n)
    else: f+=1; print("✘",n)
NOW=1789500000000
def row(t,h,s="مصدر",u="u"):
    return {"title":t,"summary":"","sourceName":s,"url":u+t[:6],"publishedAt":None,"seenAt":NOW-int(h*3600000)}
rows=[
 row("وزير الري يوجه بتحقيق في قطع أشجار حرم قناطر إدفينا بمطوبس",0.2),
 row("مذبحة قناطر إدفينا قطع أشجار حرم القناطر بمطوبس تحقيق عاجل",0.5),
 row("وزير الري لوناس بوزقزة يتابع مشاريع الربط بالولايات الداخلية",1.0),
 row("وزير الري يتابع تقدم مشاريع الربط البعدي لمحطات تحلية مياه البحر",1.1),
 row("غرق طفل في ترعة المريوطية بالجيزة والحماية المدنية تنتشل الجثة",2.0),
 row("شبكات الري في القنيطرة قديمة وأعطالها متكررة",3.0),
 row("خبر قديم جدا عن تطهير الترع في المنوفية والبحيرة",40.0),
 row("وزير الري يبحث مع سفير أوزبكستان تعزيز التعاون في الموارد المائية",6.0),
]
cl,nw,nk=B.candidates(rows,NOW)
titles=[c["row"]["title"] for c in cl]
ok("الأجنبى الصريح يُسقط", not any("بوزقزة" in t for t in titles))
ok("الشبيه بالأجنبى يُسقط", not any("الربط البعدي" in t for t in titles))
ok("القنيطرة تُسقط", not any("القنيطرة" in t for t in titles))
ok("خارج ٢٤ ساعة يُسقط", not any("قديم جدا" in t for t in titles))
ok("واقعة إدفينا عنقود واحد بمصدرين", sum(1 for c in cl if "إدفينا" in c["row"]["title"])==1 and max(c["n"] for c in cl)==2)
ok("الحدث الميدانى يبقى", any("المريوطية" in t for t in titles))

def fake_ok(text,key,url=None,timeout=0):
    return {"ok":True,"by":"cf","data":{"stories":[
        {"i":1,"cat":1,"why":"تحقيق الوزير فى قطع الأشجار"},
        {"i":99,"cat":2,"why":"رقم مخترع"},
        {"i":2,"cat":2,"why":"غرق طفل فى ترعة بالجيزة"}]}}
b,note=B.build(rows,NOW,"k",asker=fake_ok)
ok("الرقم المخترع يُهمل ولا يُسقط الموجز", b and b["n"]==2)
ok("القصة تحمل الرابط والمصدر وعدد المصادر", b and b["stories"][0]["url"] and b["stories"][0]["sources"]==2)
ok("التصنيف يُحدّ بين ١ و٤", all(1<=s["cat"]<=4 for s in b["stories"]))
b2,n2=B.build(rows,NOW,"k",asker=lambda *a,**k:{"ok":False,"code":"unavailable"})
ok("فشل البوابة لا يرمى استثناء", b2 is None and "unavailable" in n2)
b3,n3=B.build(rows[:2],NOW,"k",asker=fake_ok)
ok("مرشحون قليلون = لا موجز", b3 is None)
print("\nنجح %d — فشل %d"%(p,f))
raise SystemExit(1 if f else 0)
