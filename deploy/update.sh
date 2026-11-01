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
# الحدود: من /etc/montage/limits.conf (install.sh كيكتبو على حساب السيرفر)، وإلا الحدود القدام ديال السيرفر المشارك
MEM_MAX=1600M; [ -f /etc/montage/limits.conf ] && . /etc/montage/limits.conf
systemctl set-property darija-dubbing MemoryHigh=infinity MemoryMax=$MEM_MAX 2>/dev/null || true
# أوامر "مرة وحدة" (deploy/once/*.sh): كنشغلو كل واحد مرة وحدة فقط، باش نقدر نصلح من GitHub بلا Console
DONE="$APP_DIR/data/.once-done"; mkdir -p "$APP_DIR/data"; touch "$DONE"
for f in "$APP_DIR"/deploy/once/*.sh; do
  [ -f "$f" ] || continue
  n=$(basename "$f")
  grep -qx "$n" "$DONE" && continue
  echo ">> once: $n"; bash "$f" && echo "$n" >> "$DONE" || echo "!! $n طاح"
done
# إلا شي فيديو كلا الذاكرة كاملة، يتقتل هو بوحدو، والصفحة تبقا خدامة (بلا ما systemd يطفي الخدمة كاملة)
mkdir -p /etc/systemd/system/darija-dubbing.service.d
printf '[Service]\nOOMPolicy=continue\nNice=5\n' > /etc/systemd/system/darija-dubbing.service.d/override.conf
systemctl daemon-reload
systemctl restart darija-dubbing
sleep 3
systemctl is-active -q darija-dubbing && echo ">> تحدّث وخدام ✓" || { echo "!! الخدمة ماتشعلاتش:"; journalctl -u darija-dubbing -n 20 --no-pager; exit 1; }
}
main "$@"
