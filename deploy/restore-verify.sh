#!/usr/bin/env bash
# 별도 임시 DB로 백업을 복원해 job_postings 건수를 원본과 대조한다. postgres 사용자로 실행한다.
set -euo pipefail

if [[ $# -ne 1 || ! -f $1 ]]; then
    echo "사용법: $0 /var/backups/jobradar/YYYY-MM-DD.dump" >&2
    exit 2
fi

dump_file=$1
verify_db=jobradar_restore_verify

if [[ $(id -un) != postgres ]]; then
    echo "postgres 사용자로 실행해야 합니다: sudo -u postgres $0 ..." >&2
    exit 2
fi

cleanup() {
    dropdb --if-exists "${verify_db}"
}
trap cleanup EXIT

cleanup
createdb "${verify_db}"
pg_restore --exit-on-error --dbname="${verify_db}" "${dump_file}"

source_count=$(psql --dbname=jobradar --tuples-only --no-align -c 'SELECT count(*) FROM job_postings')
restore_count=$(psql --dbname="${verify_db}" --tuples-only --no-align -c 'SELECT count(*) FROM job_postings')

if [[ ${source_count} != "${restore_count}" ]]; then
    echo "복구 검증 실패: 원본 ${source_count}건, 복원본 ${restore_count}건" >&2
    exit 1
fi
echo "복구 검증 성공: job_postings ${source_count}건"
