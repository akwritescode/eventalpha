#!/usr/bin/env bash
# First-boot setup for the Lightsail instance (passed as user_data by Terraform; runs as root).
# Safe to re-run: every step checks before acting.
set -euo pipefail
exec > >(tee -a /var/log/eventalpha-bootstrap.log) 2>&1
echo "bootstrap start $(date -u +%FT%TZ)"

export DEBIAN_FRONTEND=noninteractive

# --- packages: Docker Engine + compose plugin from Docker's repo, automatic security updates
if ! command -v docker >/dev/null; then
  apt-get update
  apt-get install -y ca-certificates curl gnupg unattended-upgrades
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  dpkg-reconfigure -f noninteractive unattended-upgrades
fi

# --- deploy user: owns /opt/eventalpha, runs compose, same SSH key as the default ubuntu user
if ! id deploy >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --groups docker deploy
  install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
  install -m 600 -o deploy -g deploy /home/ubuntu/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
fi
install -d -o deploy -g deploy /opt/eventalpha/deploy

# --- swap: headroom for memory spikes (pg_dump, big 13F days) instead of the OOM killer
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  swapon /swapfile
  sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
fi

# --- data disk: the attached Lightsail disk, formatted once, mounted at /srv/eventalpha
MOUNT=/srv/eventalpha
if ! mountpoint -q "$MOUNT"; then
  root_disk=$(lsblk -no PKNAME "$(findmnt -no SOURCE /)")
  disk=""
  for _ in $(seq 1 60); do  # the attachment can land a little after boot
    disk=$(lsblk -dpno NAME,TYPE | awk '$2=="disk"{print $1}' | grep -v "/dev/${root_disk}$" | head -1 || true)
    [ -n "$disk" ] && break
    sleep 5
  done
  if [ -z "$disk" ]; then
    echo "no data disk found; data will live on the root volume" >&2
  else
    blkid "$disk" >/dev/null 2>&1 || mkfs.ext4 -L eventalpha-data "$disk"
    mkdir -p "$MOUNT"
    uuid=$(blkid -s UUID -o value "$disk")
    grep -q "$uuid" /etc/fstab || echo "UUID=$uuid $MOUNT ext4 defaults,nofail,noatime 0 2" >> /etc/fstab
    mount "$MOUNT"
  fi
fi

# Directories behind the bind-mounted compose volumes. Airflow runs as uid 50000;
# Postgres containers fix their own ownership on first start.
mkdir -p "$MOUNT"/{airflow-db,warehouse-db,caddy-data,redis}
install -d -o 50000 -g 0 "$MOUNT"/{airflow-logs,airflow-config,raw-data}

echo "bootstrap done $(date -u +%FT%TZ)"
