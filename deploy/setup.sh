#!/usr/bin/env bash
# تثبيت النظام على سيرفر Ubuntu (DigitalOcean). شغلو كـ root من داخل دوسي المشروع.
# فسيرفر مشترك (فيه Odoo ولا شي حاجة خرا) نقدرو نبدلو الحدود:
#   PORT=8000 CPU_QUOTA=100% MEM_MAX=2G bash deploy/setup.sh
set -e
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
PORT=${PORT:-8000}
CPU_QUOTA=${CPU_QUOTA:-100%}
MEM_HIGH=${MEM_HIGH:-1200M}
MEM_MAX=${MEM_MAX:-1600M}

if ss -ltn "sport = :$PORT" | grep -q LISTEN && ! systemctl is-active -q darija-dubbing; then
  echo "!! البور $PORT مستعمل من برنامج آخر. ختار واحد آخر: PORT=8010 bash deploy/setup.sh"; exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg libgl1 libraqm0 debian-keyring debian-archive-keyring apt-transport-https curl
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -U pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
[ -f "$APP_DIR/.env" ] || { cp "$APP_DIR/.env.example" "$APP_DIR/.env"; echo ">> عمّر المفاتيح فـ $APP_DIR/.env"; }
sed -e "s#__APP_DIR__#$APP_DIR#g" -e "s#__PORT__#$PORT#g" -e "s#__CPU_QUOTA__#$CPU_QUOTA#g" \
    -e "s#__MEM_HIGH__#$MEM_HIGH#g" -e "s#__MEM_MAX__#$MEM_MAX#g" \
    "$APP_DIR/deploy/darija-dubbing.service" > /etc/systemd/system/darija-dubbing.service
systemctl daemon-reload
systemctl enable --now darija-dubbing
systemctl restart darija-dubbing
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow "$PORT/tcp"; fi
echo ">> خدام على http://$(curl -s ifconfig.me):$PORT"
