# Deployment - NHIP QUAN

> Production chay tren AWS EC2 tai `https://nhipquan.duckdns.org`.
> Runbook van hanh day du: [AWS EC2](./runbook-aws.md).

## Kien truc production

| Thanh phan | Noi chay | Du lieu |
|---|---|---|
| Caddy + HTTPS | AWS EC2 | Chung VM |
| Web Next.js | Docker tren AWS EC2 | Image GHCR `nhipquan-web` |
| API FastAPI | Docker tren AWS EC2 | Image GHCR `nhipquan-api` |
| Worker | Docker tren AWS EC2 | Chung source voi API |
| PostgreSQL | Docker volume tren AWS EC2 | Du lieu ben vung |
| Redis | Docker volume tren AWS EC2 | Du lieu ben vung |

Docker Compose production nam tai `infra/oracle/compose.prod.yml`. Sau khi
workflow `ci` xanh, `.github/workflows/docker-ghcr.yml` build hai image
`linux/amd64` theo dung commit SHA. Workflow deploy sau do dong bo Compose,
backup PostgreSQL, chay migration, doi container va kiem tra health tren HTTPS.

## URL

- Web: `https://nhipquan.duckdns.org`
- API health: `GET https://nhipquan.duckdns.org/health`
- OpenAPI: `https://nhipquan.duckdns.org/docs`

## Deploy

```bash
git push origin main
```

Deploy AWS tu dong chi chay khi CI va build image deu xanh. Neu container moi
khong healthy, workflow tra API/web ve image `rollback` cua lan chay truoc va
giu ban backup database tai `/opt/nhipquan/backups`.

Tren EC2, file `/opt/nhipquan/.env` can toi thieu:

```bash
DOMAIN=nhipquan.duckdns.org
CA_AGENT_MODE=live
GEMINI_LIVE_VOICE_ENABLED=true
NEXT_PUBLIC_GEMINI_LIVE_VOICE_ENABLED=true
NHIPQUAN_CORS_ORIGINS=https://nhipquan.duckdns.org
NHIPQUAN_SEED_DEMO=false
NHIPQUAN_INBOX_SEED_FIXTURE=0
NHIPQUAN_PAGE_SEED_FIXTURE=0
NHIPQUAN_LOI_GIAI_SEED=0
```

Them cac API key va cau hinh kenh tin theo nhu cau. Khong commit `.env`, token,
mat khau, hay khoa truy cap vao repository.

## Chat media

File chat duoc ghi vao `/app/data/uploads/chat` trong container API. Compose
production phai mount volume ben vung vao `/app/data/uploads`; neu bo volume,
metadata tin nhan van con trong database nhung file dinh kem se mat sau khi
container bi thay the.

## Rollback

Moi image GHCR co ca tag `latest` va tag commit SHA. De rollback, dat image API
va web trong Compose ve SHA da xac minh, sau do chay:

```bash
cd /opt/nhipquan
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps
curl -fsS https://nhipquan.duckdns.org/health
```

## Xu ly su co

| Trieu chung | Kiem tra |
|---|---|
| Web trang hoac goi API loi | `NEXT_PUBLIC_API_URL` phai la `https://nhipquan.duckdns.org` luc build image web |
| CORS | `NHIPQUAN_CORS_ORIGINS` phai khop domain, khong co dau `/` cuoi. Bien nay CHI THEM origin trien khai — cac origin dev (`http://localhost:3000..3002`) luon duoc phep. Muon chan han origin dev o production: dat `NHIPQUAN_CORS_DISABLE_DEV=1` |
| File chat khong kha dung | Kiem tra volume `/app/data/uploads` va quyen ghi cua container API |
| Container khong healthy | `sudo docker compose ps` va `sudo docker compose logs --tail=200` |
| HTTPS loi | Kiem tra DuckDNS, security group port 80/443 va log Caddy |
