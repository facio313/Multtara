# PongDang ARM64 Release, Deployment, and Recovery Runbook

이 문서는 Raspberry Pi 5 운영 배포의 기준 절차다. 운영 장치에서는 소스나
Dockerfile로 이미지를 직접 빌드하지 않는다. GitHub Actions가 만든
`linux/arm64` 이미지를 GHCR digest로 고정하고, release bundle과 checksum을
검증한 뒤 배포한다.

## 1. 운영 계약

- Release source는 기존 `vMAJOR.MINOR.PATCH` Git tag가 가리키는 commit이다.
- Backend와 frontend 이미지는 GHCR의 `@sha256:<64 hex>` 참조만 허용한다.
- Release build는 max-level provenance와 SBOM attestation을 이미지에 첨부한다.
- Pi 배포는 `docker-compose.yml` 다음에 `docker-compose.deploy.yml`을 로드한다.
  이 overlay가 모든 app `build` context를 제거한다.
- `pi-deploy.sh`는 effective Compose를 다시 확인하고 `up --no-build`만 실행한다.
- 배포 전 실행 중인 DB가 있으면 검증된 PostgreSQL backup을 먼저 만든다.
- 이미지 rollback은 DB schema/data를 자동으로 되돌리지 않는다. DB restore는
  별도 명령과 명시 확인문이 필요한 유지보수 작업이다.
- Frontend origin은 `127.0.0.1`에만 bind한다. 공개 접점에는 별도의 신뢰 가능한
  HTTPS edge와 방화벽이 필요하다.
- Frontend image는 `USER nginx`와 비특권 container port `8080`을 사용하고 모든
  Linux capability를 제거한다. 쓰기가 필요한 PID/cache 경로만 tmpfs로 제공한다.
- `bonifacio.work` portfolio 배포는 `/multtara/` 아래에서만 노출한다. release
  frontend는 같은 asset/API prefix로 빌드하며 Django session/CSRF cookie도
  고유 이름과 `Path=/multtara/`로 다른 프로젝트와 격리한다.
- 일반 공개 경로는 호스트 Authelia `auth_request`로 보호한다. edge는 외부
  `Remote-*` 헤더를 버리고 검증된 값을 덮어쓰며, release frontend는
  `VITE_SSO_ENABLED=true`, backend Compose는 `PONGDANG_SSO_ENABLED=true`여야
  한다. 운영에서 로컬 가입·비밀번호 인증·계정 삭제를 다시 열지 않는다.

## 2. 최초 사용자 결정 및 외부 준비

다음 값과 외부 상태는 저장소가 대신 결정할 수 없다.

1. 배포 전용 Linux 사용자 이름. 예시는 `pongdang`이다.
2. 공개 HTTPS domain과 `ALLOWED_HOSTS`.
3. GHCR package visibility. Private이면 Pi용 read-only token과 username.
4. GitHub repository variable `VITE_KAKAO_MAP_KEY`. 지도를 사용할 때만 설정하고
   Kakao Developers에서 실제 HTTPS domain을 제한한다.
5. 50자 이상 무작위 Django `SECRET_KEY`, PostgreSQL user/database/password.
6. 공공 제공자 API key. 없는 provider는 빈 값으로 두며 안전 상태는 fail-closed다.
7. 선택형 credential-free Valhalla base URL `ROUTING_MATRIX_URL`. 비워 두면
   route matrix 기반 일정만 생성하지 않고 다른 서비스는 계속 동작한다.
8. 신뢰 가능한 HTTPS termination 및 Pi firewall 규칙.
9. off-device backup 대상과 조직의 RPO/RTO. 로컬 기본 retention은 14일이며
   off-device 복사 자체는 이 저장소가 구성하지 않는다.

현재 portfolio 서버의 운영값은 `APPLICATION_BASE_PATH=/multtara`,
`VITE_APP_BASE_PATH=/multtara/`, `VITE_API_BASE_URL=/multtara/api/v1/`,
`FRONTEND_PORT=5182`다. DB는 다른 프로젝트와 공유하지 않고 전용 Compose volume을
사용한다.

Docker Engine, Docker Compose 2.24.4 이상, Python 3, `sha256sum`, `flock`을 설치하고,
Pi OS가 64-bit ARM인지 확인한다.

```bash
uname -s
uname -m
docker compose version
```

Private GHCR package이면 배포 사용자로 로그인한다. token을 명령행 인수나
파일에 적지 않는다.

```bash
printf '%s' "$GHCR_READ_TOKEN" \
  | docker login ghcr.io --username "$GHCR_USER" --password-stdin
```

Docker group membership은 사실상 root 수준 권한이다. 전용 사용자에만 부여하고,
공용 계정이나 웹 프로세스에는 부여하지 않는다.

## 3. Release 생성

사용자가 검증된 commit에 tag를 만들고 push하면 `Release ARM64 Images` workflow가
실행된다.

```bash
git tag -s v1.0.0 <verified-commit>
git push origin v1.0.0
```

수동 재실행은 workflow dispatch에서 이미 존재하는 tag를 입력하고 그 tag가
가리키는 revision을 선택한다. 입력 tag와 workflow revision이 다르면 실패한다.

Workflow 결과:

- `ghcr.io/<owner>/<repo>/backend:<version>` 및 commit tag
- `ghcr.io/<owner>/<repo>/frontend:<version>` 및 commit tag
- 각 이미지의 registry digest, max provenance, SPDX SBOM attestation
- `pongdang-release-<version>.tar.gz`와 그 checksum
- bundle 내부의 digest-pinned `release.env`와 checksum

Pi로 옮긴 후 tar를 풀기 전에 바깥 checksum부터 확인한다.

```bash
sha256sum -c pongdang-release-v1.0.0.tar.gz.sha256
tar -xzf pongdang-release-v1.0.0.tar.gz
cd pongdang-release-v1.0.0
./scripts/pi-deploy.sh validate-release "$PWD/release.env"
```

## 4. Pi deployment target 설치

Bundle은 deployment target 밖의 임시 작업 디렉터리에 푼다. Setup은 Linux ARM64,
정확한 canonical target, 기존 marker, 사용자 Docker 접근을 확인한다. 이미지
build/pull/start는 하지 않는다.

```bash
sudo ./scripts/pi-setup.sh \
  --target /opt/pongdang \
  --deploy-user pongdang \
  --project-name pongdang
```

Setup이 생성한 `/opt/pongdang/.env`는 placeholder뿐이다. 배포 사용자로 값을
채우고 mode와 owner를 확인한다.

```bash
sudo -u pongdang editor /opt/pongdang/.env
sudo chown pongdang:pongdang /opt/pongdang/.env
sudo chmod 600 /opt/pongdang/.env
sudo -u pongdang stat -c '%U %a %n' /opt/pongdang/.env
```

필수 검증 항목:

- `POSTGRES_PASSWORD`: 16자 이상이며 placeholder가 아님
- `DATABASE_URL`: percent-encoded credential을 사용하고 `db:5432/<POSTGRES_DB>`를
  가리킴
- `SECRET_KEY`: 50자 이상 무작위 값
- `ALLOWED_HOSTS`: wildcard나 URL이 아닌 명시 host 목록
- `SECURE_SSL_REDIRECT=True`
- `FRONTEND_BIND_ADDRESS=127.0.0.1`
- `ROUTING_MATRIX_URL`: 비어 있거나 credential/userinfo 없는 HTTPS base URL

`DATABASE_URL`의 password와 `POSTGRES_PASSWORD`는 같은 credential이어야 한다.
URL의 `@`, `/`, `:`, `%` 같은 예약 문자는 percent-encode한다.

## 5. 배포와 상태 확인

Release bundle의 manifest와 checksum을 함께 보관한 상태에서 실행한다.

```bash
sudo -u pongdang /opt/pongdang/scripts/pi-deploy.sh deploy \
  --target /opt/pongdang \
  --release-file "$PWD/release.env"
```

배포 명령은 다음 순서로 동작한다.

1. target marker, 실행 사용자, ARM64, secret file mode/content 검증
2. release checksum과 네 개의 허용 field 검증
3. backend/frontend GHCR digest 검증
4. effective Compose에서 app build context 부재와 loopback origin 검증
5. 기존 DB가 실행 중이면 pre-deploy backup 생성 및 archive 검증
   - DB가 중지됐더라도 prior release state 또는 PostgreSQL volume이 있으면
     첫 배포로 간주하지 않고 중단한다. DB를 복구·검증해 backup을 만든 뒤 다시
     배포한다.
   - DB, prior release state, PostgreSQL volume이 모두 없을 때만 검증된 첫
     배포로 진행한다.
6. digest images pull
7. `up -d --no-build --wait`
8. 성공 후에만 `state/current.release.env` 갱신

확인 명령:

```bash
cd /opt/pongdang
sudo -u pongdang docker compose \
  --project-name pongdang \
  --env-file .env \
  -f docker-compose.yml \
  ps

curl --fail --silent --show-error -H 'Host: bonifacio.work' -H 'X-Forwarded-Proto: https' http://127.0.0.1:5182/api/health/
curl --fail --silent --show-error -H 'Host: bonifacio.work' -H 'X-Forwarded-Proto: https' http://127.0.0.1:5182/api/health/ready/
curl --include --silent --show-error -H 'Host: bonifacio.work' -H 'X-Forwarded-Proto: https' http://127.0.0.1:5182/api/health/integrations/
curl --include --silent --show-error -H 'Host: bonifacio.work' -H 'X-Forwarded-Proto: https' http://127.0.0.1:5182/api/health/safety/
```

이 loopback 확인은 서버 운영자 전용이다. 외부 HTTPS 경로는 Authelia 세션 없이
`302 /sso/`가 정상이며, 공개 무인 probe용 우회 경로를 추가하지 않는다.

Collector는 파생 적합도와 retention을 포함한 9개 핵심 주기 작업과, `ROUTING_MATRIX_URL` 설정 시
drive/walk/bicycle snapshot을 갱신하는 선택형 route 작업을 최대 4개 worker로
실행한다. Route refresh 기본 간격은 `ROUTE_MATRIX_INTERVAL_SECONDS=86400`이다.
컨테이너 healthcheck는 DB의 heartbeat가 900초 안에 갱신됐고 collector가 stopped
상태가 아닌지 검사한다. Docker의 `unhealthy` 표시는 자동 재시작을 보장하지
않으므로 외부 감시에서 연속 실패와 container restart count를 함께 경보한다.

인증 후 `/multtara/api/health/integrations/`의 `503`과 `status=degraded`는 웹 프로세스가 죽었다는
뜻이 아니라, 필수 pipeline 실행 이력이 아직 없거나 실제 freshness 기준을
충족하지 못했다는 fail-closed 신호다. 이를 정상 `200`으로 치환하지 말고 provider별
상태를 조사한다.

수집 성공과 안전 근거 준비는 서로 다른 신호다. 인증 후 `/multtara/api/health/safety/`는
verified/non-DEMO catalog의 현재 Water Index를 재검증하고 aggregate `counts`와
`reason_counts`를 반환한다. 현재 `CLEAR`가 하나도 없으면 `503 degraded`이며,
integrations가 `200`이어도 이 결과를 무시하지 않는다. 외부 alert에서는 다음
명령의 종료 코드와 JSON도 같은 독립 신호로 사용할 수 있다.

```bash
cd /opt/pongdang
sudo -u pongdang docker compose \
  --project-name pongdang \
  --env-file .env \
  -f docker-compose.yml \
  exec -T backend \
  python manage.py audit_safety_readiness --json --require-current-clear
```

DB disk 사용량, backup age, loopback `/api/health/ready/`도 서버 감시에 연결한다.
`json-file` log는 기본 10 MiB × 5개로 제한되지만 host journal과 HTTPS edge log도
별도 retention을 둔다.

## 6. 이미지 rollback

직전 성공 release가 있을 때만 가능하다.

```bash
sudo -u pongdang /opt/pongdang/scripts/pi-deploy.sh rollback \
  --target /opt/pongdang
```

Rollback도 현재 DB를 먼저 backup하고 digest image만 pull한다. 실패한 새 image의
migration이 DB schema를 변경했을 수 있으므로, image rollback 후에도 readiness와
핵심 query를 확인한다. 호환되지 않는 DB 변경은 아래 restore 절차를 별도 승인 후
수행한다.

## 7. PostgreSQL backup과 retention

수동 backup:

```bash
sudo -u pongdang /opt/pongdang/scripts/postgres-backup.sh \
  --target /opt/pongdang
```

결과는 `/opt/pongdang/backups/postgres/pongdang-<UTC>-<process>.dump`와
`.sha256`이다.
`pg_dump --format=custom` 성공만으로 완료 처리하지 않고, 같은 PostgreSQL image의
`pg_restore --list`가 archive를 읽어야 확정한다.

Retention dry run과 적용:

```bash
sudo -u pongdang /opt/pongdang/scripts/postgres-prune-backups.sh \
  --target /opt/pongdang --days 14

sudo -u pongdang /opt/pongdang/scripts/postgres-prune-backups.sh \
  --target /opt/pongdang --days 14 --apply
```

다음 archive는 자동 삭제하지 않는다.

- 가장 최신 backup
- checksum이 없거나 검증에 실패한 archive
- retention보다 최근인 archive

매일 실행하는 systemd timer 또는 배포 사용자 cron을 구성하되, 성공 여부와 마지막
성공 시각을 감시한다. 예시 cron은 매일 03:17에 실행한다.

```cron
17 3 * * * /opt/pongdang/scripts/postgres-backup.sh --target /opt/pongdang
```

같은 SSD의 retention은 장치 분실·SSD 고장·화재를 막지 못한다. `.dump`와
`.sha256`을 암호화된 off-device 저장소로 복제하고, 복제 완료 여부도 감시한다.

## 8. Restore

먼저 checksum과 archive 구조만 검증한다.

```bash
sudo -u pongdang /opt/pongdang/scripts/postgres-restore.sh verify \
  --target /opt/pongdang \
  --backup /opt/pongdang/backups/postgres/pongdang-YYYYMMDDTHHMMSSZ-PID.dump
```

실제 restore는 유지보수 창에 수행한다. 명령은 backend와 collector를 중지하고,
복구 직전 backup을 한 번 더 만든 뒤 application database를 drop/create한다.

```bash
sudo -u pongdang /opt/pongdang/scripts/postgres-restore.sh restore \
  --target /opt/pongdang \
  --backup /opt/pongdang/backups/postgres/pongdang-YYYYMMDDTHHMMSSZ-PID.dump \
  --confirm RESTORE:pongdang:pongdang
```

`project`나 DB 이름이 다르면 확인문도 실제 marker와 `.env` 값으로 바뀐다. Restore가
실패하면 backend와 collector는 중지 상태로 남는다. 부분 복구 DB를 자동 공개하지
말고 로그, 실패 SQL, archive와 pre-restore backup을 보존한 뒤 원인을 해결한다.

## 9. 분리된 복구 drill

분기마다 운영 volume과 다른 Compose project에서 실제 restore를 수행한다. 같은
Pi에서 시험할 경우 별도 target, project, frontend port, DB volume을 쓴다.

```bash
sudo ./scripts/pi-setup.sh \
  --target /srv/pongdang-drill \
  --deploy-user pongdang \
  --project-name pongdang-drill
```

Drill `.env`에는 별도 DB 이름·password, `FRONTEND_PORT=18080`을 사용한다. 같은
release를 먼저 deploy한 후, production archive와 checksum을 drill의
`backups/postgres/`로 복사하고 owner/mode를 복원한다.

```bash
sudo -u pongdang /srv/pongdang-drill/scripts/postgres-restore.sh verify \
  --target /srv/pongdang-drill \
  --backup /srv/pongdang-drill/backups/postgres/pongdang-YYYYMMDDTHHMMSSZ-PID.dump

sudo -u pongdang /srv/pongdang-drill/scripts/postgres-restore.sh restore \
  --target /srv/pongdang-drill \
  --backup /srv/pongdang-drill/backups/postgres/pongdang-YYYYMMDDTHHMMSSZ-PID.dump \
  --confirm RESTORE:pongdang-drill:pongdang_drill
```

Drill 증거로 다음을 기록한다.

- 사용한 release version·commit·image digests
- backup filename·checksum·생성시각·off-device 복제시각
- restore 시작/종료시각과 측정 RTO
- backup 생성시각부터 장애 가정시각까지의 측정 RPO
- 핵심 table row count와 최근 observation timestamp
- `/api/health/ready/` 및 대표 read-only API 응답
- 실패·수동 개입·다음 개선사항

복구가 한 번도 실제 custom archive에서 성공하지 않았다면 backup 체계는 검증된
것으로 간주하지 않는다.
