#!/usr/bin/env bash
# كيحيد الخدمة من السيرفر بلا مايقيس حتى حاجة خرا. الدوسي ديال المشروع كيبقى (حيدو بيدك ملي تكون نقلتي data/).
set -e
systemctl disable --now darija-dubbing 2>/dev/null || true
rm -f /etc/systemd/system/darija-dubbing.service
systemctl daemon-reload
echo ">> الخدمة تحيدات. باش تحيد كلشي: rm -rf $(cd "$(dirname "$0")/.." && pwd)"
