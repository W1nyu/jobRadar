#!/usr/bin/env bash
# Ubuntu LTS VM에서 root로 한 번 실행한다. 실행 전 /opt/jobradar에 저장소를 배치해야 한다.
set -euo pipefail

app_dir=/opt/jobradar
app_user=jobradar
uv_bin=/home/jobradar/.local/bin/uv
uv_python_dir=${app_dir}/.uv-python
domain=${JOBRADAR_DOMAIN:-jobradar.my}

if [[ ${EUID} -ne 0 ]]; then
    echo "root로 실행하세요: sudo $0" >&2
    exit 2
fi
if [[ ! -f "${app_dir}/pyproject.toml" ]]; then
    echo "${app_dir}에 jobRadar 저장소가 필요합니다." >&2
    exit 2
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates certbot curl fail2ban git nginx pipx postgresql postgresql-contrib python3 python3-venv ufw

if ! id "${app_user}" >/dev/null 2>&1; then
    adduser --system --group --home /home/${app_user} --shell /usr/sbin/nologin "${app_user}"
fi
chown -R "${app_user}:${app_user}" "${app_dir}"
# systemd에서 실행할 셸 스크립트에 chmod를 적용하므로, Windows 작업본에서 온 Git이
# 실행 비트만으로 pull을 막지 않도록 서버 복제본에서는 이를 추적하지 않는다.
runuser -u "${app_user}" -- git -C "${app_dir}" config core.filemode false
# systemd는 ProtectHome으로 /home을 차단한다. Python 런타임은 앱 디렉터리에 둬야
# .venv의 인터프리터 심볼릭 링크를 서비스가 따라갈 수 있다.
runuser -u "${app_user}" -- pipx install --force uv
install -d -o "${app_user}" -g "${app_user}" -m 0755 "${uv_python_dir}"
runuser -u "${app_user}" -- env UV_PYTHON_INSTALL_DIR="${uv_python_dir}" \
    "${uv_bin}" python install --directory "${app_dir}" 3.12
rm -rf "${app_dir}/.venv"

if ! swapon --show=NAME --noheadings | grep -q '^/swapfile$'; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
cat >/etc/sysctl.d/99-jobradar.conf <<'EOF'
vm.swappiness=10
EOF
sysctl --system >/dev/null

pg_major=$(pg_lsclusters --no-header | awk 'NR == 1 {print $1}')
if [[ -z "${pg_major}" ]]; then
    echo "PostgreSQL 클러스터 버전을 찾지 못했습니다." >&2
    exit 2
fi
pg_conf_dir="/etc/postgresql/${pg_major}/main/conf.d"
if [[ ! -d "${pg_conf_dir}" ]]; then
    echo "PostgreSQL 설정 경로를 찾지 못했습니다: ${pg_conf_dir}" >&2
    exit 2
fi
install -D -m 0644 "${app_dir}/deploy/postgresql.tuning.conf" "${pg_conf_dir}/jobradar.conf"
systemctl restart postgresql

install -d -m 0755 /var/www/jobradar-acme
install -d -o postgres -g postgres -m 0700 /var/backups/jobradar
install -m 0644 "${app_dir}/deploy/nginx-rate-limit.conf" /etc/nginx/conf.d/jobradar-rate-limit.conf
sed "s/__JOBRADAR_DOMAIN__/${domain}/g" "${app_dir}/deploy/nginx-jobradar-http.conf" >/etc/nginx/sites-available/jobradar
ln -sfn /etc/nginx/sites-available/jobradar /etc/nginx/sites-enabled/jobradar
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

install -m 0644 "${app_dir}/deploy/jobradar-api.service" /etc/systemd/system/jobradar-api.service
install -m 0644 "${app_dir}/deploy/jobradar-worker.service" /etc/systemd/system/jobradar-worker.service
install -m 0644 "${app_dir}/deploy/jobradar-backup.service" /etc/systemd/system/jobradar-backup.service
install -m 0644 "${app_dir}/deploy/jobradar-backup.timer" /etc/systemd/system/jobradar-backup.timer
install -d -o root -g root -m 0755 /usr/local/lib/jobradar
install -o root -g root -m 0755 \
    "${app_dir}/deploy/backup.sh" \
    "${app_dir}/deploy/restore-verify.sh" \
    /usr/local/lib/jobradar/
chmod 0750 \
    "${app_dir}/deploy/backup.sh" \
    "${app_dir}/deploy/restore-verify.sh" \
    "${app_dir}/deploy/deploy.sh" \
    "${app_dir}/deploy/bootstrap-server.sh" \
    "${app_dir}/deploy/enable-https.sh"
systemctl daemon-reload
systemctl enable jobradar-backup.timer

ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat >/etc/ssh/sshd_config.d/90-jobradar.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sshd -t
systemctl reload ssh

install -d -m 0755 /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/90-jobradar.conf <<'EOF'
[Journal]
SystemMaxUse=200M
MaxRetentionSec=14day
EOF
systemctl restart systemd-journald

echo "초기화 완료. 다음으로 PostgreSQL jobradar 역할·DB와 ${app_dir}/.env를 만들고 deploy.sh를 실행하세요."
