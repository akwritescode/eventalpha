# Deploying EventAlpha to AWS Lightsail

One Lightsail instance runs the same compose stack as local development, with a production
layer on top. Nothing here runs automatically: CI builds images, you deploy from your laptop.

```
internet :80/:443 ──► Caddy (Let's Encrypt) ──► api:8081           eventalpha.duckdns.org
you ──► ssh -L 8080:localhost:8080 ──► airflow-apiserver:8080      (never public)

/srv/eventalpha (attached disk): warehouse-db, airflow-db, Redis AOF, logs, raw data, Caddy certificates
Lightsail bucket: raw/ (landing JSONL), warehouse/ (nightly pg_dump, 30-day retention)
```

| Piece | Where |
|---|---|
| Infrastructure | `infra/terraform` (instance, static IP, 64 GB disk, firewall, bucket + key) |
| First-boot setup | `infra/bootstrap.sh` (Docker, deploy user, swap, mounts the disk) |
| Production compose layer | `docker-compose.prod.yml`, `deploy/Caddyfile` |
| Images | CI (`.github/workflows/ci.yml`) pushes `ghcr.io/akwritescode/eventalpha-{airflow,api}:<sha>` on main |
| Deploy / rollback | `deploy/deploy.sh [sha]` |
| Backups, cleanup, disk alerts | `dags/maintenance.py` |

## One-time setup

1. **DuckDNS:** sign in at duckdns.org and claim `eventalpha`. Copy the token.
2. **Telegram:** create a bot with @BotFather, message it once, then read your chat id from
   `https://api.telegram.org/bot<token>/getUpdates`. The same bot gets DAG failures (from
   Airflow) and high-impact events (from the API's Redis consumer group).
3. **healthchecks.io:** create a check with schedule `0 7 * * 2-6` (UTC) and 3 h grace. The
   events DAG pings it after each weekday's filings land.
4. **Infrastructure:**
   ```bash
   cd infra/terraform
   cp terraform.tfvars.example terraform.tfvars      # set ssh_allowed_cidrs to your IP/32
   terraform init && terraform apply
   terraform output -raw bucket_secret_access_key     # for .env.production
   ```
5. **DNS:** in DuckDNS, point `eventalpha` at `terraform output static_ip` (the duckdns
   container keeps it updated afterwards).
6. **SSH alias** in `~/.ssh/config`:
   ```
   Host eventalpha
     HostName <static_ip>
     User deploy
   ```
7. **Production env:** `cp .env.example .env.production` and fill in every production value.
   Generate passwords with `openssl rand -base64 24` and a Fernet key with
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   Set `RAW_BUCKET` and `BACKUP_BUCKET` to the bucket name, and `AWS_ACCESS_KEY_ID` /
   `AWS_SECRET_ACCESS_KEY` to the bucket key.
8. **GHCR visibility:** after the first CI run on main, make both packages public
   (GitHub → Packages → Package settings), or `docker login ghcr.io` on the server once with a
   read-only token.

## Deploy, roll back, operate

```bash
deploy/deploy.sh               # deploy HEAD (CI must have built it)
deploy/deploy.sh 3f2c1ab...    # roll back to an earlier commit
ssh -L 8080:localhost:8080 eventalpha     # Airflow UI at http://localhost:8080 (admin / AIRFLOW_ADMIN_PASSWORD)
ssh eventalpha 'cd /opt/eventalpha && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail 100 api'
```

Migrations run on every deploy (`warehouse-migrate` before the scheduler and API start).
Keep them backward-compatible (add before you remove) so a rollback never meets a schema it
doesn't understand.

## Restore a backup

```bash
aws s3 cp s3://<bucket>/warehouse/2026/11/14/eventalpha-....dump /tmp/w.dump   # bucket key credentials
docker compose ... exec -T warehouse-db pg_restore -U eventalpha -d eventalpha --clean --if-exists < /tmp/w.dump
```

## Later

* Real domain: set `API_DOMAIN`, add an A record, redeploy. Caddy issues the certificate itself.
* Deploy from CI: needs SSH reachable from GitHub runners (e.g. the Tailscale GitHub Action)
  instead of opening port 22 to the world.
* Remote Terraform state (S3 backend) once more than one machine runs `terraform apply`.
