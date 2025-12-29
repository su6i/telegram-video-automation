# Scan & Resume Guide

## خصوصیات

✅ **Incremental Scanning**: اگر manifest قبلی وجود دارد، تنها ویدیوهای جدید اسکن می‌شوند.
✅ **No Limit by Default**: بدون محدودیت، **تمام** ویدیوها اسکن می‌شوند.
✅ **Optional Limit**: می‌توان برای تست با `--limit N` محدود کرد.

## استفاده

### اسکن کامل (اولین بار)
```bash
./scan.sh
```
⏱️ **مدت**: 10-15 دقیقه برای 85 ویدیو

### اسکن Incremental (ویدیوهای جدید)
```bash
./scan.sh
```
✅ دوباره اجرا می‌کند و تنها ویدیوهای جدید اضافه می‌کند

### برای تست (محدود به 10 ویدیو)
```bash
./scan.sh --limit 10
```

### برای تست دوباره (بدون محدودیت)
```bash
./scan.sh
```

## چه اتفاقی می‌افتد؟

**اول (run 1):**
```
📋 Found 0 existing videos in manifest
✅ Found 85 NEW videos (0 + 85 = 85 total).
```

**دوم (run 2 - اگر ویدیوهای جدید اضافه شده باشند):**
```
📋 Found 85 existing videos in manifest
✅ Found 3 NEW videos (85 + 3 = 88 total).
```

**اگر نیچ نو ویدیو نیست:**
```
📋 Found 85 existing videos in manifest
✅ Scan complete. 85 total videos in library.
```

## دانلود

```bash
./download.sh
```

📁 تمام ویدیوها در `downloads/Course/Section/` دانلود می‌شوند.

## Upload

```bash
./upload_to_telegram.sh --intro
```

🎥 ویدیوها به تلگرام آپلود می‌شوند.
