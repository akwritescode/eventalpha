variable "region" {
  type    = string
  default = "us-east-1"
}

variable "availability_zone" {
  type    = string
  default = "us-east-1a"
}

variable "name" {
  type    = string
  default = "eventalpha"
}

# 8 GB / 2 vCPU. List current bundles: aws lightsail get-bundles --query 'bundles[].[bundleId,ramSizeInGb,price]'
variable "instance_bundle_id" {
  type    = string
  default = "large_3_0"
}

variable "data_disk_gb" {
  type    = number
  default = 64
}

# Lightsail object storage: medium_1_0 = 100 GB. Holds raw/ landing files and warehouse/ dumps.
variable "bucket_bundle_id" {
  type    = string
  default = "medium_1_0"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_ed25519.pub"
}

# SSH is only open to these CIDRs (your IP as x.x.x.x/32, plus GitHub Actions if deploying from CI).
variable "ssh_allowed_cidrs" {
  type = list(string)
}
