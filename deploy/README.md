# M11 서버 배포 순서

원격 저장소가 `origin`으로 설정된 깨끗한 복제본을 `/opt/jobradar`에 두고, Ubuntu 22.04 LTS에서 진행한다.
`.env`는 저장소에 커밋하지 않고 `/opt/jobradar/.env`에 `jobradar:jobradar`, 권한 `600`으로 저장한다.

```bash
sudo JOBRADAR_DOMAIN=jobradar.my /opt/jobradar/deploy/bootstrap-server.sh

# PostgreSQL은 Unix 소켓 peer 인증을 쓴다. app systemd가 jobradar 사용자로 실행되므로
# DB 비밀번호를 .env에 보관할 필요가 없다.
sudo -u postgres psql
CREATE ROLE jobradar LOGIN;
CREATE DATABASE jobradar OWNER jobradar;
\q

sudo -u jobradar cp /opt/jobradar/.env.example /opt/jobradar/.env
sudo -u jobradar chmod 600 /opt/jobradar/.env
# .env: APP_ENV=production, APP_BASE_URL=https://jobradar.my, LOG_JSON=true,
# DATABASE_URL=postgresql+psycopg://jobradar@/jobradar?host=/var/run/postgresql 및 API·알림 키를 설정한다.

sudo /opt/jobradar/deploy/deploy.sh
sudo /opt/jobradar/deploy/enable-https.sh jobradar.my <Let's Encrypt 알림 이메일>
sudo systemctl enable --now jobradar-api jobradar-worker
sudo systemctl start jobradar-backup.service
sudo -u postgres /opt/jobradar/deploy/restore-verify.sh /var/backups/jobradar/$(date -u +%F).dump
```

복구 리허설은 `jobradar_restore_verify`라는 임시 DB만 만들고 삭제한다. 운영 DB `jobradar`는 수정하지 않는다.
