# CLAUDE.md — telegram-video-automation

## قوانین Agent

### قوانین مشترک (از agent-constitution)
تمام فایل‌های `.agent/constitution/rules/` را بخوان و رعایت کن.
`.agent/constitution` یک symlink به کلونِ مرکزی مشترک است (نه submodule).
آپدیت: `git -C ~/@-github/agent-constitution pull --ff-only`

### قوانین اختصاصی این پروژه
تمام فایل‌های `.agent/local-rules/` را بخوان.
در صورت تناقض، **قوانین اختصاصی (local-rules) اولویت دارند.**
