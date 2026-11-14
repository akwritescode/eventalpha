#!/usr/bin/env bash
# Deploy a commit to the Lightsail server from your laptop.
#
#   deploy/deploy.sh            deploy HEAD (its images must already be in GHCR: CI pushes them on main)
#   deploy/deploy.sh <sha>      deploy / roll back to a specific commit
#
# Needs: an SSH alias "eventalpha" (or EVENTALPHA_HOST) for deploy@<static ip>, and
# .env.production (git-ignored) with the production values from .env.example.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${EVENTALPHA_HOST:-eventalpha}"
TAG="${1:-$(git rev-parse HEAD)}"
REGISTRY="${IMAGE_REGISTRY:-ghcr.io/akwritescode}"
ENV_FILE=.env.production
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE (copy .env.example and fill in production values)"; exit 1; }
for image in eventalpha-airflow eventalpha-api; do
  docker manifest inspect "$REGISTRY/$image:$TAG" >/dev/null 2>&1 \
    || { echo "image $REGISTRY/$image:$TAG not found; has CI built this commit?"; exit 1; }
done

echo "→ deploying $TAG to $HOST"
scp -q docker-compose.yml docker-compose.prod.yml "$HOST:/opt/eventalpha/"
scp -q deploy/Caddyfile "$HOST:/opt/eventalpha/deploy/Caddyfile"
# The tag goes into the server's .env so restarts and reboots keep running this release.
{ grep -vE '^(IMAGE_TAG|IMAGE_REGISTRY)=' "$ENV_FILE"; echo "IMAGE_TAG=$TAG"; echo "IMAGE_REGISTRY=$REGISTRY"; } \
  | ssh "$HOST" 'umask 077 && cat > /opt/eventalpha/.env'

ssh "$HOST" "cd /opt/eventalpha && $COMPOSE pull --quiet && $COMPOSE up -d --remove-orphans && docker image prune -f >/dev/null"

domain=$(grep -E '^API_DOMAIN=' "$ENV_FILE" | cut -d= -f2-)
echo "→ waiting for https://$domain/actuator/health"
for _ in $(seq 1 30); do
  if curl -fsS "https://$domain/actuator/health" >/dev/null 2>&1; then
    echo "✓ $TAG is live at https://$domain"
    exit 0
  fi
  sleep 10
done
echo "✗ health check failed; inspect with: ssh $HOST 'cd /opt/eventalpha && $COMPOSE ps && $COMPOSE logs --tail 100'"
exit 1
