# ==========================================
# Terraform Variables
# ==========================================
# All sensitive or environment-specific values
# should be set via terraform.tfvars (not committed)
# or environment variables (TF_VAR_*)
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
  default     = "t3.small"  # Minimum for sentence-transformers model
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

# ==================== SECURITY VARIABLES ====================
# These MUST be configured for production deployments

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into the server (e.g., your IP or VPN). MUST be set in production."
  type        = list(string)
  default     = []  # Empty = no SSH access (safe default)

  validation {
    condition     = length(var.allowed_ssh_cidrs) > 0 || var.environment == "development"
    error_message = "allowed_ssh_cidrs must be set for production deployments."
  }
}

variable "allowed_admin_cidrs" {
  description = "CIDR blocks allowed to access Prometheus, Grafana, and direct app port. Use VPN or office IPs."
  type        = list(string)
  default     = []  # Empty = no admin access from outside

  validation {
    condition     = length(var.allowed_admin_cidrs) > 0 || var.environment == "development"
    error_message = "allowed_admin_cidrs must be set for production deployments to access monitoring."
  }
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "development"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

variable "enable_https" {
  description = "Whether HTTPS is enabled (requires domain and certificate)"
  type        = bool
  default     = false
}

variable "domain_name" {
  description = "Domain name for the application (optional, for HTTPS setup)"
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for HTTPS (required if enable_https = true)"
  type        = string
  default     = ""
}

# ==================== MONITORING VARIABLES ====================

variable "enable_monitoring" {
  description = "Whether to deploy Prometheus and Grafana"
  type        = bool
  default     = true
}

variable "grafana_admin_password" {
  description = "Initial Grafana admin password (change after first login)"
  type        = string
  sensitive   = true
  default     = ""  # Should be set via terraform.tfvars or TF_VAR_grafana_admin_password
}

variable "prometheus_retention_days" {
  description = "Prometheus data retention period"
  type        = number
  default     = 15
}

# ==================== APPLICATION VARIABLES ====================

variable "docker_image" {
  description = "Docker image to deploy"
  type        = string
  default     = "yourdockerhub/resume-intelligence:latest"
}

variable "jwt_secret_key" {
  description = "JWT secret key for authentication (generate with: openssl rand -base64 32)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "admin_password_hash" {
  description = "Bcrypt hash of admin password (generate with backend auth module)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "cors_origins" {
  description = "Comma-separated list of allowed frontend origins"
  type        = string
  default     = ""
}
