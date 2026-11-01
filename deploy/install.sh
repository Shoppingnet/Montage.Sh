#!/usr/bin/env bash
# تنصيب كامل بأمر واحد على سيرفر Ubuntu جديد (كـ root):
#   curl -fsSL https://raw.githubusercontent.com/Shoppingnet/Montage.Sh/ccr-9ae395ba-8t0l4a/deploy/install.sh | bash
# كيحمّل المشروع من GitHub فـ /opt/Montage.Sh، كينصب كولشي، كيفعّل التحديث الأوتوماتيكي، وكيحدد الموارد على حساب السيرفر.
set -e
REPO=${REPO:-https://github.com/Shoppingnet/Montage.Sh}
BRANCH=${BRANCH:-ccr-9ae395ba-8t0l4a}
APP_DIR=${APP_DIR:-/opt/Montage.Sh}
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq git curl >/dev/null
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q && git -C "$APP_DIR" checkout -q "$BRANCH" && git -C "$APP_DIR" pull -q --ff-only
else
  git clone -q -b "$BRANCH" "$REPO" "$APP_DIR"
fi
# الموارد: سيرفر بوحدو = كناخدو كولشي تقريبا؛ سيرفر مشارك (SHARED=1) = النص
CORES=$(nproc); MEM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
if [ "${SHARED:-0}" = "1" ]; then CPU_Q=$(( CORES * 50 ))%; MEM_X=$(( MEM_MB * 55 / 100 ))M; HEAVY=1; LIGHT=2
else CPU_Q=$(( CORES * 95 ))%; MEM_X=$(( MEM_MB * 85 / 100 ))M; HEAVY=$(( CORES > 2 ? CORES - 1 : 1 )); LIGHT=$(( CORES > 2 ? 3 : 2 )); fi
mkdir -p /etc/montage
printf 'PORT=%s\nCPU_QUOTA=%s\nMEM_MAX=%s\n' "${PORT:-8000}" "$CPU_Q" "$MEM_X" > /etc/montage/limits.conf
PORT=${PORT:-8000} CPU_QUOTA=$CPU_Q MEM_HIGH=infinity MEM_MAX=$MEM_X bash "$APP_DIR/deploy/setup.sh"
# الإعدادات ديال الخدامة على حساب النوى (ماكنمسوش المفاتيح)
sed -i "s/^LIGHT_WORKERS=.*/LIGHT_WORKERS=$LIGHT/; s/^HEAVY_WORKERS=.*/HEAVY_WORKERS=$HEAVY/" "$APP_DIR/.env"
grep -q '^FFMPEG_THREADS=' "$APP_DIR/.env" || echo "FFMPEG_THREADS=$(( CORES > 2 ? 2 : 1 ))" >> "$APP_DIR/.env"
grep -q '^API_TOKEN=' "$APP_DIR/.env" || echo "API_TOKEN=$(openssl rand -hex 24)" >> "$APP_DIR/.env"
# swap صغير باش مايطيحش الفيديو الكبير
if [ ! -f /swapfile ] && [ "$MEM_MB" -lt 16000 ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
bash "$APP_DIR/deploy/update.sh"
bash "$APP_DIR/deploy/auto-update.sh" --install
IP=$(curl -s -4 ifconfig.me || hostname -I | awk '{print $1}')
echo
echo "================================================================"
echo ">> تنصب ✓   $CORES نوى / ${MEM_MB}MB   الخدامة: $LIGHT خفاف + $HEAVY مونتاج"
echo ">> الواجهة:  http://$IP:${PORT:-8000}"
echo ">> المفاتيح: nano $APP_DIR/.env   (GEMINI_API_KEY, ELEVENLABS_API_KEY, ANTHROPIC_API_KEY, APP_PASSWORD)"
echo ">> من بعد:   systemctl restart darija-dubbing"
echo ">> API_TOKEN ديال الموظفين الآليين: $(grep '^API_TOKEN=' $APP_DIR/.env | cut -d= -f2)"
echo "================================================================"
