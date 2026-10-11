#!/usr/bin/env bash
# كيشوف واش كاين تحديث فـ GitHub، وإلا كان كيطبقو. كيتشغل بوحدو كل 5 دقايق (cron).
# التفعيل (مرة وحدة):  bash /opt/Montage.Sh/deploy/auto-update.sh --install
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
if [ "$1" = "--install" ]; then
  (crontab -l 2>/dev/null | grep -v auto-update.sh; echo "*/5 * * * * bash $APP_DIR/deploy/auto-update.sh >> /var/log/montage-update.log 2>&1") | crontab -
  echo ">> التحديث الأوتوماتيكي مفعّل (كل 5 دقايق). اللوگ: /var/log/montage-update.log"; exit 0
fi
if [ "$1" = "--remove" ]; then
  crontab -l 2>/dev/null | grep -v auto-update.sh | crontab -; echo ">> التحديث الأوتوماتيكي تحيّد"; exit 0
fi
cd "$APP_DIR" && git fetch -q || exit 0
[ "$(git rev-parse HEAD)" = "$(git rev-parse '@{u}')" ] && exit 0
echo "$(date '+%F %T') كاين تحديث: $(git log -1 --format=%s '@{u}')"
bash "$APP_DIR/deploy/update.sh"
