# Deploying EventAlpha to AWS Lightsail

One Lightsail instance runs the same compose stack as local development, with a production
layer on top: CI builds images, you deploy from your laptop. The web UI is separate: Vercel
builds and serves `web/` straight from GitHub, and browsers call the API on Lightsail.

```
browser ──► Vercel (web UI, static) ─ page only                    eventalpha.vercel.app
browser ──► :443 Caddy (Let's Encrypt) ──► api:8081 (REST + SSE)   eventalpha.duckdns.org
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
| Web UI | Vercel project with root directory `web/` (`web/vercel.json`); deploys on push to main, preview per PR |
| Backups, cleanup, disk alerts | `dags/maintenance.py` |

## One-time setup

1. **DuckDNS:** sign in at duckdns.org and claim `eventalpha`. Copy the token.
2. **Telegram:** create a bot with @BotFather, message it once, then read your chat id from
   `https://api.telegram.org/bot<token>/getUpdates`. The same bot gets DAG failures (from
   Airflow) and high-impact events (from the API's Redis consumer group).
3. **healthchecks.io:** create a check with cron `0 2 * * 2-6`, timezone `America/New_York`, and 3 h grace. The
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
   `python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` (the format `Fernet.generate_key()` produces, no extra package needed).
   Set `RAW_BUCKET` and `BACKUP_BUCKET` to the bucket name, and `AWS_ACCESS_KEY_ID` /
   `AWS_SECRET_ACCESS_KEY` to the bucket key.
8. **GHCR visibility:** after the first CI run on main, make both packages public
   (GitHub → Packages → Package settings), or `docker login ghcr.io` on the server once with a
   read-only token.

9. **Web UI on Vercel:**
   1. vercel.com → Add New → Project → import the GitHub repo; **Root Directory** `web`
      (framework, build and output come from `web/vercel.json`).
   2. Environment variables (Production and Preview):
      `REACT_APP_API_URL=https://eventalpha.duckdns.org` and
      `REACT_APP_TELEGRAM_URL=<channel invite link>`. They're baked in at build time, so
      redeploy after changing them.
   3. In `.env.production`, allow the site to call the API, then `deploy/deploy.sh`:
      `EVENTALPHA_CORS_ALLOWED_ORIGINS=https://eventalpha.vercel.app,https://eventalpha-*.vercel.app`
      (use the project's real domain; the wildcard covers preview builds; add a custom
      domain here too if you attach one).
   4. Check: open the Vercel URL; the stream loads and shows LIVE. A CORS error in the
      browser console means the origin isn't in that list.

   The browser talks to the API directly, not through a Vercel rewrite: Vercel's proxy isn't
   meant for long-lived Server-Sent Events, and the live stream would keep reconnecting.

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

The index-membership release renames `minute_universe_members` to `index_members` in
revision `d2f4a6b8c0e1`. Stop the existing scheduler before deploying this release so its
candle collector cannot access the old table during the migration. If rolling back across
this release, stop the scheduler and run
`docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --entrypoint bash warehouse-migrate -c 'cd /opt/airflow/project && alembic downgrade b6a729ce18f0'`
with the index-membership release still selected, then deploy the earlier image.

## Restore a backup

```bash
aws s3 cp s3://<bucket>/warehouse/2026/11/14/eventalpha-....dump /tmp/w.dump   # bucket key credentials
docker compose ... exec -T warehouse-db pg_restore -U eventalpha -d eventalpha --clean --if-exists < /tmp/w.dump
```

## Later

* Real domain: set `API_DOMAIN`, add an A record, redeploy. Caddy issues the certificate itself.
* Deploy the backend from CI: needs SSH reachable from GitHub runners (e.g. the Tailscale
  GitHub Action). The web UI already deploys from GitHub through Vercel.
  instead of opening port 22 to the world.
* Remote Terraform state (S3 backend) once more than one machine runs `terraform apply`.
