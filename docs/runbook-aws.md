# Runbook — Deploy NHỊP QUÁN lên AWS EC2 (Singapore) với Free Plan

> Mục tiêu: toàn bộ stack (Postgres + Redis + API + worker + web) trên **1 EC2 thật**,
> tên miền riêng + HTTPS, vùng Singapore (~60ms từ VN).
> **Chi phí:** $200 credit + 6 tháng Free Plan (tài khoản tạo sau 15/07/2025) —
> t3.small ~$14/tháng → credit phủ trọn 6 tháng. Hết 6 tháng: ~$14/tháng,
> hoặc đóng gói dữ liệu và chuyển sang hạ tầng khác.
> So sánh nền tảng: [`research-oracle-cloud.md`](./research-oracle-cloud.md) ·
> [`research-google-cloud.md`](./research-google-cloud.md). Tổng quan production: [`deployment.md`](./deployment.md).

## 0. Điều kiện

- ✅ Thẻ tín dụng quốc tế (Visa/Master credit hoặc debit quốc tế — AWS chấp nhận rộng hơn Oracle).
- ✅ SĐT nhận OTP.

## 1. Đăng ký AWS (10 phút)

1. **https://portal.aws.amazon.com/billing/signup**
2. Email chưa từng dùng với AWS → password → **Continue**.
3. Account type: **Personal** (Business không cần lúc này).
4. Contact info: địa chỉ VN, SĐT — AWS gọi/OTP xác minh.
5. Thẻ tín dụng: authorize tạm ~1-2 USD rồi hoàn.
6. **Support plan**: chọn **Basic support — Free**.
7. Sau khi vào console: gõ **EC2** vào thanh tìm kiếm → region selector (góc phải trên) → chọn
   **Asia Pacific (Singapore) ap-southeast-1**.

> ⚠️ **Chống cháy tiền:** Billing → Budgets → tạo budget $5/tháng với alert 100%.
> Free plan hết 6 tháng AWS **không tự trừ tiền** nhưng để an toàn: sau khi hết
> credit, xóa instance nếu không muốn trả tiếp (§8).

## 2. Tạo SSH key (PowerShell trên máy bạn)

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\nhipquan_aws -N '""'
```

EC2 console → **Network & Security → Key Pairs → Create key pair** → name `nhipquan-aws`
→ type **ED25519** → *Import* file `.pub` (mở bằng notepad copy).

## 3. Tạo EC2 instance (5 phút)

1. EC2 console → **Launch instance**.
2. **Name**: `nhipquan-prod`
3. **AMI**: Ubuntu Server 24.04 LTS (free tier eligible).
4. **Instance type**: **t3.small** (2 vCPU, 2GB RAM — đủ full stack + swap 4G).
   *(t3.micro 1GB quá sát cho ortools + Postgres; small là an toàn.)*
5. **Key pair**: `nhipquan-aws`.
6. **Network settings** → *Edit*:
   - VPC mặc định · subnet mặc định · **Auto-assign public IP: Enable**
   - Security group: **Create** `nhipquan-sg` mở 3 rule:
     - SSH (22) — source **My IP** (không All!)
     - HTTP (80) — Anywhere 0.0.0.0/0
     - HTTPS (443) — Anywhere 0.0.0.0/0
7. **Storage**: 20 GiB gp3 (đủ compose + data; credit dư sức).
8. **Advanced details** → *User data* → dán toàn bộ nội dung
   [`infra/aws/user-data.yaml`](../infra/aws/user-data.yaml) → *Summary* → **Launch instance**.
9. Chờ ~2 phút → chọn instance → copy **Public IPv4**.

## 4. Tên miền DuckDNS (2 phút)

1. **https://www.duckdns.org** → login GitHub/Google → tạo subdomain (vd `nhipquan`).
2. Dán **Public IPv4 của EC2** → *Update*.

## 5. Duyệt workflow build image

Sau khi workflow `ci` xanh, `.github/workflows/docker-ghcr.yml` build image
`linux/amd64` và push GHCR theo đúng commit SHA trên `main`.
Lần đầu chạy vào GitHub repo → tab **Actions** → nếu hiển thị chờ duyệt workflow mới →
**Approve and run**. Chờ build xong (~3-5 phút, 2 jobs xanh).

> Image GHCR private mặc định. VM cần pull:
> tạo Personal Access Token (classic) scope `read:packages` → dùng khi `docker login ghcr.io`.

## 6. Lên stack (5 phút, SSH)

```powershell
ssh -i $env:USERPROFILE\.ssh\nhipquan_aws ubuntu@<EC2_PUBLIC_IP>
```

```bash
[ -f /var/lib/nhipquan-bootstrapped ] && echo "bootstrap OK"
sudo cp /opt/nhipquan/repo/.env.example /opt/nhipquan/.env
sudo nano /opt/nhipquan/.env
```

Nội dung `.env` tối thiểu:

```bash
DOMAIN=nhipquan.duckdns.org
CA_AGENT_MODE=live            # AI thật (điền GROQ_API_KEY bên dưới) hoặc replay
GROQ_API_KEY=sk-...
NHIPQUAN_CORS_ORIGINS=https://nhipquan.duckdns.org
NHIPQUAN_SEED_DEMO=false
NHIPQUAN_INBOX_SEED_FIXTURE=0
NHIPQUAN_PAGE_SEED_FIXTURE=0
NHIPQUAN_LOI_GIAI_SEED=0
# kênh tin FB/Telegram/Zalo/SMTP nếu dùng — copy từ .env máy dev
```

```bash
# Pull image (private GHCR → login bằng PAT read:packages)
sudo docker login ghcr.io -u KanTrun
cd /opt/nhipquan
sudo docker compose up -d
sudo docker compose ps                  # chờ 5 services healthy
curl -fsS https://nhipquan.duckdns.org/health   # HTTPS đã có cert Let's Encrypt
```

### Nạp nền dữ liệu demo trên AWS

Nếu stack đã chạy rồi, thực hiện trên EC2 để nạp 19 tài khoản, lịch tuần,
menu/BOM, nguyên liệu, tồn kho, đơn mẫu, Cẩm nang và SOP:

```bash
sudo sed -i 's/^NHIPQUAN_SEED_DEMO=.*/NHIPQUAN_SEED_DEMO=true/' /opt/nhipquan/.env
grep -q '^NHIPQUAN_SEED_DEMO=' /opt/nhipquan/.env || echo 'NHIPQUAN_SEED_DEMO=true' | sudo tee -a /opt/nhipquan/.env
cd /opt/nhipquan
sudo docker compose pull api
sudo docker compose up -d --force-recreate api
sudo docker compose logs --tail=100 api
```

Log thành công có dòng `NHIP QUAN demo foundation loaded (idempotent)` và các
chỉ số `users=19`, `shifts=21`, `menu=8`, `inventory_items=8`. Sau khi kiểm tra
xong, tắt cờ để những lần restart sau không chạy lại seed:

```bash
sudo sed -i 's/^NHIPQUAN_SEED_DEMO=.*/NHIPQUAN_SEED_DEMO=false/' /opt/nhipquan/.env
sudo docker compose up -d --force-recreate api
sudo docker compose ps
curl -fsS https://nhipquan.duckdns.org/health
```

## 7. Deploy lại khi code đổi

`git push origin main` sẽ chạy chuỗi tự động: CI → build hai image GHCR theo
SHA → backup PostgreSQL → migration → deploy → health check HTTPS. Workflow
không deploy nếu CI đỏ hoặc phát hiện bất kỳ cờ demo/fixture nào đang bật.

## 8. Hết 6 tháng Free Plan — 3 lựa chọn

1. **Tiếp tục trả** ~$14/tháng (t3.small + 20GB gp3, region Singapore) — không cần đổi gì.
2. **Đóng gói:** `sudo docker compose down` → snapshot EBS → terminate instance
   (giữ snapshot ~$2/tháng nếu muốn hồi sinh sau).
3. **Chuyển hạ tầng:** backup PostgreSQL và thư mục upload, triển khai Compose
   trên VM mới, rồi cập nhật DuckDNS sang IP mới.

## 9. Sự cố thường gặp

| Triệu chứng | Xử lý |
|---|---|
| Signup thẻ bị từ chối | Thử debit quốc tế (Visa/Master có thanh toán online), hoặc credit thật. AWS rộng hơn Oracle. |
| Web trắng / API lỗi | `NHIPQUAN_CORS_ORIGINS` phải khớp domain (không `/` cuối); `docker compose logs api -f` |
| Solve chậm | Swap đã có 4G; kiểm `docker stats`; t3.small đủ cho solve 60s của quán nhỏ |
| Let's Encrypt fail | Chờ 1-2 phút sau lần request đầu; kiểm DuckDNS trỏ đúng IP; port 80/443 mở SG |
| Không SSH được | SG rule SSH source = IP nhà bạn (đổi IP thì update rule); đúng key file, `chmod 400` trên Linux |
| Deploy đỏ `no space left on device` (containerd) | Ổ 20GB cạn do dở dang layer pull hoặc image cũ tích lũy: SSH vào chạy `sudo rm -rf /var/lib/containerd/io.containerd.content.v1.content/ingest/* && sudo docker image prune -a -f`. Khuyến nghị: tăng EBS lên 30GB trên AWS Console (EC2 → Volumes → Modify Volume → 30 GiB, không cần reboot). |

## 10. Pham vi AWS production

AWS EC2 chay tron stack tren mot VM: Caddy, web, API, worker, PostgreSQL va
Redis. Du lieu can duoc backup dinh ky; khi het credit, quyet dinh tiep tuc tra
phi hoac chuyen Compose sang VM khac truoc khi terminate instance.
