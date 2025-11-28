provider "aws" {
  region = "eu-central-1"
}

resource "aws_security_group" "banking_sg" {
  name        = "banking-sg"
  description = "Banking app security group"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # THIS IS THE FIX - prevents recreation if it already exists
  lifecycle {
    create_before_destroy = true
    prevent_destroy       = true
  }

  tags = {
    Name = "banking-sg"
  }
}

# Rest stays the same...
resource "aws_instance" "banking_server" {
  count         = 2

  ami           = "ami-0084a47cc718c111a"
  instance_type = "t3.small"
  key_name      = "bank"

  vpc_security_group_ids = [aws_security_group.banking_sg.id]

  user_data = <<-EOF
              #!/bin/bash
              apt-get update
              apt-get install -y docker.io docker-compose git
              systemctl start docker
              systemctl enable docker
              usermod -aG docker ubuntu

              mkdir -p /home/ubuntu/banking
              chown ubuntu:ubuntu /home/ubuntu/banking
              EOF

  tags = {
    Name = "Banking-Server-${count.index + 1}"
  }
}

output "server_ips" {
  value = aws_instance.banking_server[*].public_ip
}

output "server_1_ip" {
  value = aws_instance.banking_server[0].public_ip
}

output "server_2_ip" {
  value = aws_instance.banking_server[1].public_ip
}
