#!/usr/bin/env bash
# كيشوف واش كاين تحديث فـ GitHub، وإلا كان كيطبقو. كيتشغل بوحدو كل 5 دقايق (cron).
# التفعيل (مرة وحدة):  bash /opt/Montage.Sh/deploy/auto-update.sh --install
main() {
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
# ماكنعاودوش نشعلو الخدمة وسط شي فيديو كيتصاوب، كنتسناو الدورة الجاية (إلا ما تحرك حتى شي حاجة 30 دقيقة = مبلوكي، كنحدثو)
DB=$(grep -s '^DATA_DIR=' .env | cut -d= -f2); DB="${DB:-./data}/jobs.db"
if [ -f "$DB" ] && python3 -c "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);sys.exit(0 if c.execute(\"SELECT COUNT(*) FROM jobs WHERE (status IN ('analyzing','editing','rendering') OR img_status='working') AND updated > strftime('%s','now') - 1800\").fetchone()[0] else 1)" "$DB"; then
  # ماكنتسناوش أكثر من 20 دقيقة (يمكن الفيديو هو اللي مبلوكي)
  P=/tmp/montage-update-pending; [ -f $P ] || date +%s > $P
  if [ $(( $(date +%s) - $(cat $P) )) -lt 1200 ]; then
    echo "$(date '+%F %T') كاين تحديث ولكن شي فيديو كيتصاوب دابا، غنتسناو"; exit 0
  fi
fi
rm -f /tmp/montage-update-pending
echo "$(date '+%F %T') كاين تحديث: $(git log -1 --format=%s '@{u}')"
bash "$APP_DIR/deploy/update.sh"
}
# الدالة كاملة كتتقرا قبل ما تخدم: git pull اللي كيبدل هاد الملف مايخربقش التنفيذ
main "$@"; exit
