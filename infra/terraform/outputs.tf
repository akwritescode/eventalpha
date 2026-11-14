output "static_ip" {
  value = aws_lightsail_static_ip.this.ip_address
}

output "bucket" {
  value = aws_lightsail_bucket.data.name
}

output "bucket_access_key_id" {
  value = aws_lightsail_bucket_access_key.server.access_key_id
}

output "bucket_secret_access_key" {
  value     = aws_lightsail_bucket_access_key.server.secret_access_key
  sensitive = true
}

output "ssh" {
  value = "ssh deploy@${aws_lightsail_static_ip.this.ip_address}"
}
