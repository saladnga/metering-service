terraform {
    required_providers {
      aws = {
        source = "hashicorp/aws"
        version = "~> 5.0"
      }
    }
}

provider "aws" {
  region = "us-east-1"
}

data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "metering" {
  name = "metering-sg-tf"
  description = "For metering service (Terraform-managed)"
  vpc_id = data.aws_vpc.default.id

  ingress {
    description = "SSH from my IP"
    from_port = 22
    to_port = 22
    protocol = "tcp"
    cidr_blocks = ["184.93.47.67/32"]
  }

  ingress {
    description = "API"
    from_port = 8000
    to_port = 8000
    protocol = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "metering" {
  ami = "ami-0b6d9d3d33ba97d99"
  instance_type = "t3.micro"
  key_name = "metering-key"
  vpc_security_group_ids = [aws_security_group.metering.id]
  iam_instance_profile = aws_iam_instance_profile.metering_ec2.name

  tags = {
    Name = "metering-service-tf"
  }
}

resource "aws_s3_bucket" "archive" {
  bucket = "metering-service-344626620635-tf"
}

resource "aws_s3_bucket_lifecycle_configuration" "archive" {
  bucket = aws_s3_bucket.archive.id

  rule {
    id = "expire-old-archives"
    status = "Enabled"

    filter {
      
    }

    expiration {
      days = 90
    }
  }
}

resource "aws_ecr_repository" "metering" {
  name = "metering-service-tf"
}

resource "aws_iam_role" "metering_ec2" {
  name = "metering-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
        Effect = "Allow"
        Principal = {
            Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecr_pull" {
  role = aws_iam_role.metering_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role = aws_iam_role.metering_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "metering_ec2" {
  name = "metering-ec2-profile"
  role = aws_iam_role.metering_ec2.name
}

variable "db_password" {
  type      = string
  sensitive = true
}

resource "aws_ssm_parameter" "db_password" {
  name  = "/metering-service/db-password"
  type  = "SecureString"
  value = var.db_password
}

