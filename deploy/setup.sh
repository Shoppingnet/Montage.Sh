#!/usr/bin/env bash
# تثبيت النظام على سيرفر Ubuntu (DigitalOcean). شغلو كـ root من داخل دوسي المشروع.
set -e
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg libgl1 libraqm0 debian-keyring debian-archive-keyring apt-transport-https curl
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -U pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
[ -f "$APP_DIR/.env" ] || { cp "$APP_DIR/.env.example" "$APP_DIR/.env"; echo ">> عمّر المفاتيح فـ $APP_DIR/.env"; }
sed "s#__APP_DIR__#$APP_DIR#g" "$APP_DIR/deploy/darija-dubbing.service" > /etc/systemd/system/darija-dubbing.service
systemctl daemon-reload
systemctl enable --now darija-dubbing
echo ">> خدام على http://$(curl -s ifconfig.me):8000"
