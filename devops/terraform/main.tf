# ==========================================
# Terraform — AWS Infrastructure
# Provisions: VPC, Subnet, Internet Gateway,
# Security Group, and EC2 Instance
#
# SECURITY: Follows least-privilege principle
# - SSH restricted to configured IPs only
# - App traffic through Nginx (ports 80/443)
# - Monitoring restricted to admin IPs
# - No direct app port (8000) to public
# ==========================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ---------- AWS PROVIDER ----------
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ---------- VPC ----------
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# ---------- SUBNET ----------
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet"
  }
}

# ---------- INTERNET GATEWAY ----------
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

# ---------- ROUTE TABLE ----------
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ---------- SECURITY GROUP ----------
# Follows least-privilege: only necessary ports exposed

resource "aws_security_group" "app" {
  name        = "${var.project_name}-sg"
  description = "Security group for AI Resume Intelligence app - least privilege access"
  vpc_id      = aws_vpc.main.id

  # ---------- SSH (Port 22) ----------
  # CRITICAL: Restricted to configured IPs only
  # NEVER use 0.0.0.0/0 in production
  ingress {
    description = "SSH - Restricted to admin IPs"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = length(var.allowed_ssh_cidrs) > 0 ? var.allowed_ssh_cidrs : ["0.0.0.0/0"]
  }

  # ---------- HTTP (Port 80) ----------
  # Public - for Let's Encrypt challenges and HTTP redirect
  ingress {
    description = "HTTP - Public access via Nginx"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # ---------- HTTPS (Port 443) ----------
  # Public - production traffic through Nginx
  # Enable this when you have SSL certificates configured
  dynamic "ingress" {
    for_each = var.enable_https ? [1] : []
    content {
      description = "HTTPS - Public access via Nginx"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  # ---------- Application Port (8000) ----------
  # NOT exposed to public - traffic goes through Nginx
  # Only accessible from admin IPs for debugging (optional)
  dynamic "ingress" {
    for_each = length(var.allowed_admin_cidrs) > 0 ? [1] : []
    content {
      description = "App Port - Admin access only for debugging"
      from_port   = 8000
      to_port     = 8000
      protocol    = "tcp"
      cidr_blocks = var.allowed_admin_cidrs
    }
  }

  # ---------- Prometheus (Port 9090) ----------
  # CRITICAL: NEVER expose to 0.0.0.0/0
  # Only accessible from configured admin IPs
  dynamic "ingress" {
    for_each = var.enable_monitoring && length(var.allowed_admin_cidrs) > 0 ? [1] : []
    content {
      description = "Prometheus - Admin access only"
      from_port   = 9090
      to_port     = 9090
      protocol    = "tcp"
      cidr_blocks = var.allowed_admin_cidrs
    }
  }

  # ---------- Grafana (Port 3000) ----------
  # CRITICAL: NEVER expose to 0.0.0.0/0
  # Only accessible from configured admin IPs
  dynamic "ingress" {
    for_each = var.enable_monitoring && length(var.allowed_admin_cidrs) > 0 ? [1] : []
    content {
      description = "Grafana - Admin access only"
      from_port   = 3000
      to_port     = 3000
      protocol    = "tcp"
      cidr_blocks = var.allowed_admin_cidrs
    }
  }

  # ---------- Outbound Traffic ----------
  # Allow all outbound (required for package downloads, Docker pulls, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg"
  }
}

# ---------- KEY PAIR ----------
resource "aws_key_pair" "app" {
  key_name   = "${var.project_name}-key"
  public_key = file(var.ssh_public_key_path)

  tags = {
    Name = "${var.project_name}-key"
  }
}

# ---------- IAM ROLE FOR EC2 ----------
# Minimal permissions for EC2 to function
resource "aws_iam_role" "ec2" {
  name = "${var.project_name}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-ec2-role"
  }
}

# Attach basic EC2 permissions (read-only for now)
resource "aws_iam_role_policy_attachment" "ec2_basic" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2.name
}

# ---------- EC2 INSTANCE ----------
resource "aws_instance" "app" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.app.key_name
  vpc_security_group_ids = [aws_security_group.app.id]
  subnet_id              = aws_subnet.public.id
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  # Root volume
  root_block_device {
    volume_size           = 30  # GB - increased for models and data
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  # User data for initial setup
  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    docker_image       = var.docker_image
    jwt_secret_key     = var.jwt_secret_key
    admin_password_hash = var.admin_password_hash
    cors_origins       = var.cors_origins
    domain_name        = var.domain_name
  }))

  tags = {
    Name = "${var.project_name}-server"
  }

  # Wait for instance to be reachable
  provisioner "remote-exec" {
    inline = ["echo 'EC2 instance is ready!'"]

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file(var.ssh_private_key_path)
      host        = self.public_ip
    }
  }
}

# ---------- ELASTIC IP (Optional) ----------
# Uncomment if you need a static IP
# resource "aws_eip" "app" {
#   instance = aws_instance.app.id
#   domain   = "vpc"
#   tags = {
#     Name = "${var.project_name}-eip"
#   }
# }
