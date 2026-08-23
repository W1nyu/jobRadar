#!/usr/bin/env bash
# root로 실행한다. 저장소와 .env는 jobradar 소유여야 하며, origin 원격이 설정돼 있어야 한다.
set -euo pipefail

app_dir=/opt/jobradar
app_user=jobradar
uv_bin=/home/jobradar/.local/bin/uv

if [[ ${EUID} -ne 0 ]]; then
    echo "root로 실행하세요: sudo /opt/jobradar/deploy/deploy.sh" >&2
    exit 2
fi
if [[ ! -f "${app_dir}/.env" ]]; then
    echo "${app_dir}/.env가 없습니다. .env.example을 복사해 운영 값을 먼저 입력하세요." >&2
    exit 2
fi
if [[ ! -x ${uv_bin} ]]; then
    echo "${uv_bin}을 찾지 못했습니다. bootstrap-server.sh로 uv를 설치하세요." >&2
    exit 2
fi

runuser -u "${app_user}" -- git -C "${app_dir}" pull --ff-only
runuser -u "${app_user}" -- "${uv_bin}" sync --frozen --no-dev --directory "${app_dir}"
runuser -u "${app_user}" -- "${uv_bin}" run --directory "${app_dir}" alembic upgrade head

systemctl daemon-reload
systemctl restart jobradar-api.service jobradar-worker.service
systemctl --no-pager --full status jobradar-api.service jobradar-worker.service
curl --fail --silent --show-error http://127.0.0.1:8000/readyz >/dev/null
