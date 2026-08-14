# ==========================================
# Terraform Outputs
# ==========================================
# These values are shown after `terraform apply`
# and used to configure Ansible inventory.

output "instance_public_ip" {
  description = "Public IP of the EC2 instance"
  value       = aws_instance.app.public_ip
}

output "instance_id" {
  description = "EC2 Instance ID"
  value       = aws_instance.app.id
}

output "app_url" {
  description = "Application URL"
  value       = "http://${aws_instance.app.public_ip}"
}

output "api_docs_url" {
  description = "API Documentation URL"
  value       = "http://${aws_instance.app.public_ip}/docs"
}

output "ssh_command" {
  description = "SSH command to connect to the server"
  value       = "ssh -i ~/.ssh/resume-app-key.pem ubuntu@${aws_instance.app.public_ip}"
}

output "ansible_inventory_entry" {
  description = "Copy this into Ansible inventory.ini"
  value       = "resume-server ansible_host=${aws_instance.app.public_ip} ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/resume-app-key.pem"
}
