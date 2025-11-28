provider "aws" {
  region = "eu-central-1"
}

resource "aws_security_group" "banking_web" {
  name        = "banking-web-sg"
  description = "Allow HTTP, HTTPS, SSH"

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

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "banking_server" {
  ami           = "ami-0084a47cc718c111a"
  instance_type = "t3.small"
  key_name      = "bank"
  
  vpc_security_group_ids = [aws_security_group.banking_web.id]
  
  user_data = <<-EOF
              #!/bin/bash
              apt-get update
              apt-get install -y docker.io docker-compose git
              systemctl start docker
              systemctl enable docker
              usermod -aG docker ubuntu
              EOF
  
  tags = {
    Name = "Banking-Server"
  }
}

output "server_ip" {
  value = aws_instance.banking_server.public_ip
}
