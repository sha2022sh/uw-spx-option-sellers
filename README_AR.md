# نظام أبو وسام - SPX Option Sellers Pro

## الفكرة
هذا المشروع يسحب بيانات Unusual Whales API بسرعة، ويطلع لك:
- Call Wall
- Put Wall
- Gamma Wall
- Max Pain
- أكثر 5 عقود تداولًا
- جدول قيم جاهزة لإدخالها في مؤشر TradingView

## التشغيل

1) ثبّت Python 3.11 أو أحدث.

2) افتح المجلد وشغّل:

```bash
pip install -r requirements.txt
cp .env.example .env
```

3) افتح ملف `.env` وضع مفتاح Unusual Whales API:

```bash
UNUSUAL_WHALES_API_KEY=YOUR_KEY
```

4) شغل السيرفر:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## الروابط المهمة

إخراج JSON كامل:

```bash
http://127.0.0.1:8000/levels/SPX
```

إخراج نص جاهز للنسخ في TradingView:

```bash
http://127.0.0.1:8000/pine/SPX
```

مع تاريخ أو انتهاء:

```bash
http://127.0.0.1:8000/levels/SPX?date=2026-05-20&expiry=2026-05-22
```

## أفضل إعداد سرعة
- CACHE_SECONDS=20 أو 30
- شغل السيرفر محليًا على نفس الجهاز
- لا تخلي التحديث أقل من 10 ثواني حتى لا تستهلك API
- استخدم `/pine/SPX` للنسخ السريع

## مهم
TradingView Pine لا يستطيع قراءة API مباشرة، لذلك السيرفر يعطيك الأرقام جاهزة ثم تدخلها في إعدادات المؤشر.
