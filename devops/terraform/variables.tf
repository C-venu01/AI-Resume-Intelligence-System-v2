# ==========================================
# Terraform Variables
# ==========================================

variable "project_name" {
  description = "Project name used for tagging resources"
  type        = string
  default     = "resume-intelligence"
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "ap-south-1"  # Mumbai — closest to India
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t2.micro"  # Free tier eligible
}

variable "ami_id" {
  description = "Ubuntu 22.04 LTS AMI ID (update for your region)"
  type        = string
  default     = "ami-0f5ee92e2d63afc18"  # Ubuntu 22.04 ap-south-1
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key for EC2 access"
  type        = string
  default     = "~/.ssh/resume-app-key.pub"
}

variable "ssh_private_key_path" {
  description = "Path to SSH private key for EC2 access"
  type        = string
  default     = "~/.ssh/resume-app-key.pem"
}
