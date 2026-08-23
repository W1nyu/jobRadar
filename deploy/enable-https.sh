#!/usr/bin/env bash
# DNS A 레코드와 80 포트가 준비된 뒤 root로 실행한다.
set -euo pipefail

if [[ ${EUID} -ne 0 || $# -ne 2 ]]; then
    echo "사용법: sudo $0 <도메인> <Let's Encrypt 알림 이메일>" >&2
    exit 2
fi

domain=$1
email=$2
app_dir=/opt/jobradar

certbot certonly --webroot --webroot-path /var/www/jobradar-acme \
    --domain "${domain}" --email "${email}" --agree-tos --non-interactive
sed "s/__JOBRADAR_DOMAIN__/${domain}/g" "${app_dir}/deploy/nginx-jobradar.conf" >/etc/nginx/sites-available/jobradar
nginx -t
systemctl reload nginx
systemctl enable --now certbot.timer
