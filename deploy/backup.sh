#!/usr/bin/env bash
# PostgreSQL custom-format 덤프는 자체 압축을 사용한다. 이 스크립트는 postgres 사용자로 실행한다.
set -euo pipefail

backup_dir=/var/backups/jobradar
timestamp=$(date -u +%F)
target="${backup_dir}/${timestamp}.dump"
temporary="${target}.tmp"

umask 077
install -d -m 0700 "${backup_dir}"
flock -n "${backup_dir}/backup.lock" /usr/bin/pg_dump --format=custom --file="${temporary}" jobradar
mv "${temporary}" "${target}"
find "${backup_dir}" -type f -name '*.dump' -mtime +7 -delete
