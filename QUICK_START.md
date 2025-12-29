# 📚 Quick Start Guide

## تک‌دستور برای همه چیز

### ✅ دانلود تمام منابع (Videos + Pages + Resources):
```bash
./download-everything.sh
```

این یکی‌پس‌یکی انجام می‌دهد:
1. ✅ تمام **videos** را دانلود می‌کند
2. ✅ تمام **صفحات course** را به‌صورت HTML archive می‌کند
3. ✅ تمام **links و descriptions** را استخراج می‌کند

---

## ساختار نتیجه

```
Project/
├── downloads/
│   ├── 01_AI_Creator_Course/
│   │   ├── 01_Course_Intro/
│   │   │   ├── 001_Welcome.mp4
│   │   │   └── ...
│   │   └── ...
│   ├── 02_Ultimate_Video_Editing/
│   ├── 03_Viral_Video_Effects/
│   └── 04_Weekend_Youtuber/
│
└── .storage/
    ├── downloaded_video.txt          # Manifest
    ├── scraped_content.json          # Descriptions + Links
    ├── all_links.json                # تمام resource links
    ├── page_archives/                # HTML Pages
    │   ├── course_intro/
    │   │   ├── index.html
    │   │   ├── metadata.json
    │   │   └── images/
    │   └── ...
    └── descriptions/                 # Text descriptions
        ├── Welcome.txt
        └── ...
```

---

## چه داریم؟

### 📼 Videos (در `downloads/`)
- مرتب‌شده براساس دوره و بخش
- فایل‌های MP4 با کیفیت بالا
- نام‌های واضح و numbered

### 📚 HTML Pages (در `.storage/page_archives/`)
- تمام صفحات course
- **همه تصاویر** دانلود شده
- **تمام links** استخراج شده
- **metadata.json** برای هرصفحه

### 🔗 Resource Links (در `.storage/all_links.json`)
- تمام download links
- تمام resource links
- تمام external references
- **JSON format** برای استفاده آسان

### 📝 Descriptions (در `.storage/descriptions/`)
- متن کامل هر lesson
- جداگانه برای هر video
- **UTF-8** برای فارسی یا متون دیگر

---

## مثال استفاده

```bash
# Setup (یکبار)
bash setup-permissions.sh

# اولین‌بار (Scan + Download)
python scripts/smart_scraper.py --scan
./download-everything.sh

# بار دوم (فقط دانلود)
./download-everything.sh
```

---

## نکات مهم

✅ **خودکار**: هر دستور قبل‌ازیاد folderهایی که نیاز دارد می‌سازد
✅ **مرتب**: فایل‌ها براساس دوره و بخش سازمان‌دهی شده
✅ **ایمن**: اگر فایل وجود داشت، **دوباره دانلود نمی‌کند**
✅ **سریع**: می‌تواند چند video را **موازی** دانلود کند

---

## پاک کردن فایل‌های دانلود شده

```bash
# حذف تمام videos
rm -rf downloads/

# حذف تمام archives
rm -rf .storage/page_archives/

# حذف resource links
rm .storage/all_links.json

# حذف descriptions
rm -rf .storage/descriptions/
```

---

## مشاکل متداول

### ❌ "دستور پیدا نشد"
```bash
bash setup-permissions.sh
./download-everything.sh
```

### ❌ "خطای Python"
```bash
pip install -r requirements.txt
```

### ❌ "کمیسیون دانلود" (بخشی دانلود نشد)
```bash
# دوباره دانلود کنید - خودکار ادامه می‌دهد
./download-everything.sh
```

---

**سوالات؟** ببینید README.md یا کد script‌ها
