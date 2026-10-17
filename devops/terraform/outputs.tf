# ==========================================
# Terraform Outputs
# ==========================================
# These values are shown after `terraform apply`
# and used to configure Ansible inventory.
#
# SECURITY NOTE: None of these outputs contain secrets.
# Sensitive values are marked `sensitive` to prevent
# accidental display in logs.

output "instance_public_ip" {
  description = "Public IP of the EC2 instance"
  value       = aws_instance.app.public_ip
}

output "instance_id" {
  description = "EC2 Instance ID"
  value       = aws_instance.app.id
}

output "app_url" {
  description = "Application URL (HTTP)"
  value       = "http://${aws_instance.app.public_ip}"
}

output "app_url_https" {
  description = "Application URL (HTTPS, if enabled)"
  value       = var.enable_https ? "https://${var.domain_name}" : "HTTPS not enabled"
}

output "api_docs_url" {
  description = "API Documentation URL (development only)"
  value       = var.environment == "development" ? "http://${aws_instance.app.public_ip}/docs" : "Docs disabled in production"
}

output "ssh_command" {
  description = "SSH command to connect to the server"
  value       = "ssh -i ${var.ssh_private_key_path} ubuntu@${aws_instance.app.public_ip}"
  sensitive   = false
}

output "monitoring_access" {
  description = "How to access monitoring services (only from allowed admin CIDRs)"
  value       = var.enable_monitoring ? "Prometheus: http://${aws_instance.app.public_ip}:9090 (admin CIDRs only)\nGrafana: http://${aws_instance.app.public_ip}:3000 (admin CIDRs only)" : "Monitoring disabled"
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.app.id
}

output "ansible_inventory_entry" {
  description = "Copy this into Ansible inventory.ini"
  value       = "resume-server ansible_host=${aws_instance.app.public_ip} ansible_user=ubuntu ansible_ssh_private_key_file=${var.ssh_private_key_path}"
}

output "deployment_reminders" {
  description = "Important post-deployment steps"
  value = <<-EOT

    ⚠️  POST-DEPLOYMENT CHECKLIST:

    1. Change the default admin password:
       - SSH into the server
       - Generate a new password hash: docker exec -it resume-intelligence python auth.py hash-password 'YourNewPassword'
       - Update ADMIN_PASSWORD_HASH in /opt/resume-intelligence/.env
       - Restart: docker restart resume-intelligence

    2. Configure HTTPS:
       - Point your domain to ${aws_instance.app.public_ip}
       - Install certbot: apt-get install certbot python3-certbot-nginx
       - Run: certbot --nginx -d yourdomain.com

    3. Restrict SSH access:
       - Update allowed_ssh_cidrs in terraform.tfvars to your IP only
       - Run: terraform apply

    4. Set up database backups:
       - Configure automated backups to S3
       - Test restore procedure

    5. Review security group rules:
       - Verify no unintended ports are exposed
       - Check admin CIDR restrictions

  EOT
}
