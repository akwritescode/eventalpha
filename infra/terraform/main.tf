resource "aws_lightsail_key_pair" "this" {
  name       = "${var.name}-key"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "aws_lightsail_instance" "this" {
  name              = var.name
  availability_zone = var.availability_zone
  blueprint_id      = "ubuntu_24_04"
  bundle_id         = var.instance_bundle_id
  key_pair_name     = aws_lightsail_key_pair.this.name
  # Lightsail prepends its own setup lines to user_data, so a #!/bin/bash line is no longer
  # first and the script runs under /bin/sh (where `set -o pipefail` is an error). Ship the
  # script base64-encoded and run it with bash explicitly.
  user_data = "echo ${filebase64("${path.module}/../bootstrap.sh")} | base64 -d > /root/eventalpha-bootstrap.sh && bash /root/eventalpha-bootstrap.sh"

  tags = { project = var.name }

  lifecycle {
    # user_data only runs at first boot, and changing it replaces the instance. Edits to
    # bootstrap.sh apply to new instances; re-run it by hand on a running one (it's idempotent).
    ignore_changes = [user_data]
  }
}

resource "aws_lightsail_static_ip" "this" {
  name = "${var.name}-ip"
}

resource "aws_lightsail_static_ip_attachment" "this" {
  static_ip_name = aws_lightsail_static_ip.this.name
  instance_name  = aws_lightsail_instance.this.name
}

# Data (Postgres, logs, Caddy certificates) lives on this disk, not the instance root, so the
# instance can be replaced or resized without a restore. bootstrap.sh formats and mounts it.
resource "aws_lightsail_disk" "data" {
  name              = "${var.name}-data"
  size_in_gb        = var.data_disk_gb
  availability_zone = var.availability_zone
}

resource "aws_lightsail_disk_attachment" "data" {
  disk_name     = aws_lightsail_disk.data.name
  instance_name = aws_lightsail_instance.this.name
  disk_path     = "/dev/xvdf"
}

resource "aws_lightsail_instance_public_ports" "this" {
  instance_name = aws_lightsail_instance.this.name

  # Every CIDR list is spelled out: left unset, AWS fills in defaults and the provider then
  # plans to replace this resource on every apply (briefly dropping the firewall rules).
  port_info {
    protocol   = "tcp"
    from_port  = 22
    to_port    = 22
    cidrs      = var.ssh_allowed_cidrs
    ipv6_cidrs = []
  }
  port_info {
    protocol   = "tcp"
    from_port  = 80
    to_port    = 80 # Let's Encrypt HTTP-01 challenge, then redirect to HTTPS
    cidrs      = ["0.0.0.0/0"]
    ipv6_cidrs = ["::/0"]
  }
  port_info {
    protocol   = "tcp"
    from_port  = 443
    to_port    = 443
    cidrs      = ["0.0.0.0/0"]
    ipv6_cidrs = ["::/0"]
  }
  port_info {
    protocol   = "udp"
    from_port  = 443
    to_port    = 443 # HTTP/3
    cidrs      = ["0.0.0.0/0"]
    ipv6_cidrs = ["::/0"]
  }
}

resource "aws_lightsail_bucket" "data" {
  name      = "${var.name}-data-${random_id.bucket.hex}"
  bundle_id = var.bucket_bundle_id
}

resource "random_id" "bucket" {
  byte_length = 3
}

# Credentials the server uses for RAW_BUCKET / BACKUP_BUCKET (scoped to this bucket only).
resource "aws_lightsail_bucket_access_key" "server" {
  bucket_name = aws_lightsail_bucket.data.name
}
