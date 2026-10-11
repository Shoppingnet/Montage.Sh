#!/usr/bin/env bash
# كينزل آخر نسخة من GitHub ويعاود يشعل الخدمة. شغلو كـ root:  bash /opt/Montage.Sh/deploy/update.sh
# أول مرة غيطلب Username (Shoppingnet) و Password (توكن GitHub Read-only) وكيحفظهم فالسيرفر.
set -e
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$APP_DIR"
git config credential.helper store
git pull --ff-only
"$APP_DIR/venv/bin/pip" install -q -r requirements.txt
systemctl restart darija-dubbing
sleep 3
systemctl is-active -q darija-dubbing && echo ">> تحدّث وخدام ✓" || { echo "!! الخدمة ماتشعلاتش:"; journalctl -u darija-dubbing -n 20 --no-pager; exit 1; }
