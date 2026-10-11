#!/usr/bin/env bash
# كينزل آخر نسخة من GitHub ويعاود يشعل الخدمة. شغلو كـ root:  bash /opt/Montage.Sh/deploy/update.sh
# أول مرة غيطلب Username (Shoppingnet) و Password (توكن GitHub Read-only) وكيحفظهم فالسيرفر.
set -e
main() {
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$APP_DIR"
git config credential.helper store
git pull --ff-only
"$APP_DIR/venv/bin/pip" install -q -r requirements.txt
# بلا MemoryHigh: كان كيبطّئ الخدمة حتى كتولي مبلوكية. MemoryMax كيبقا باش Odoo مايتضررش
systemctl set-property darija-dubbing MemoryHigh=infinity MemoryMax=1600M 2>/dev/null || true
# إلا شي فيديو كلا الذاكرة كاملة، يتقتل هو بوحدو، والصفحة تبقا خدامة (بلا ما systemd يطفي الخدمة كاملة)
mkdir -p /etc/systemd/system/darija-dubbing.service.d
printf '[Service]\nOOMPolicy=continue\nNice=5\n' > /etc/systemd/system/darija-dubbing.service.d/override.conf
systemctl daemon-reload
systemctl restart darija-dubbing
sleep 3
systemctl is-active -q darija-dubbing && echo ">> تحدّث وخدام ✓" || { echo "!! الخدمة ماتشعلاتش:"; journalctl -u darija-dubbing -n 20 --no-pager; exit 1; }
}
main "$@"
