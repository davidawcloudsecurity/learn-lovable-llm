
# Define AWS as the provider with the specified region.
provider "aws" {
  region = "us-east-1"
}

# Create an AWS VPC with the specified CIDR block and tags.
resource "aws_vpc" "demo_main_vpc" {
  count                = var.create_vpc ? 1 : 0
  cidr_block           = var.main_cidr_block
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name = var.project_tag
  }
}

# Internet Gateway
resource "aws_internet_gateway" "demo_igw" {
  count  = var.create_vpc ? 1 : 0
  vpc_id = var.create_vpc ? aws_vpc.demo_main_vpc[0].id : null
  tags = {
    Name = "${var.project_tag}-igw"
  }
}

# Data source for existing VPC (when not creating new one)
data "aws_vpc" "existing" {
  count = var.create_vpc ? 0 : 1

  filter {
    name   = "tag:Name"
    values = [var.project_tag]
  }
}

resource "aws_subnet" "public_subnet_01" {
  count                   = var.create_vpc ? length(var.public_subnet_cidrs) : 0
  vpc_id                  = var.create_vpc ? aws_vpc.demo_main_vpc[0].id : null
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true
  tags = {
    Name = "${var.project_tag}-pb-sub-01"
  }
}

# Data source for existing public subnets
data "aws_subnets" "existing_public" {
  count = var.create_vpc ? 0 : 1

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.existing[0].id]
  }

  filter {
    name   = "tag:Name"
    values = ["${var.project_tag}-pb-sub-01"]
  }
}

resource "aws_subnet" "private_subnet_01" {
  count             = var.create_vpc ? length(var.private_subnet_cidrs) : 0
  vpc_id            = var.create_vpc ? aws_vpc.demo_main_vpc[0].id : null
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.azs[count.index]
  tags = {
    Name = "${var.project_tag}-pv-sub-01"
  }
}

# Public Route Table
resource "aws_route_table" "public_rt" {
  count  = var.create_vpc ? 1 : 0
  vpc_id = var.create_vpc ? aws_vpc.demo_main_vpc[0].id : null

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = var.create_vpc ? aws_internet_gateway.demo_igw[0].id : null
  }

  tags = {
    Name = "${var.project_tag}-public-rt"
  }
}

# Associate public subnets with public route table
resource "aws_route_table_association" "public_rta" {
  count          = var.create_vpc ? length(aws_subnet.public_subnet_01) : 0
  subnet_id      = aws_subnet.public_subnet_01[count.index].id
  route_table_id = aws_route_table.public_rt[0].id
}

# Security Group for ALB (internet-facing)
resource "aws_security_group" "alb_sg" {
  count       = var.create_vpc ? 1 : 0
  name        = "${var.project_tag}-alb-sg"
  description = "Security group for ALB"
  vpc_id      = aws_vpc.demo_main_vpc[0].id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = ["pl-3b927c52"]
    description     = "Allow HTTP from CloudFront (com.amazonaws.global.cloudfront.origin-facing)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_tag}-alb-sg"
  }
}

# Security Group for Frontend — only allows traffic from ALB
resource "aws_security_group" "frontend_sg" {
  count       = var.create_vpc ? 1 : 0
  name        = "${var.project_tag}-frontend-sg"
  description = "Security group for frontend EC2"
  vpc_id      = aws_vpc.demo_main_vpc[0].id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_tag}-frontend-sg"
  }
}

# Security Group for Backend — only allows traffic from within VPC
resource "aws_security_group" "backend_sg" {
  count       = var.create_vpc ? 1 : 0
  name        = "${var.project_tag}-backend-sg"
  description = "Security group for backend EC2"
  vpc_id      = aws_vpc.demo_main_vpc[0].id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.frontend_sg[0].id]
    description     = "Allow traffic from frontend EC2"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_tag}-backend-sg"
  }
}

# IAM Role for EC2 instances
resource "aws_iam_role" "ec2_role" {
  name = "${var.project_tag}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.project_tag}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

resource "aws_iam_role_policy_attachment" "ssm_policy" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# IAM Policy for Bedrock access
resource "aws_iam_policy" "bedrock_policy" {
  name        = "${var.project_tag}-bedrock-policy"
  description = "Policy for Bedrock access including models, knowledge bases, guardrails, and marketplace"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:GetFoundationModel",
          "bedrock:ListFoundationModels",
          "bedrock:Converse",
          "bedrock:ConverseStream"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:Retrieve",
          "bedrock:RetrieveAndGenerate"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:ApplyGuardrail"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe",
          "aws-marketplace:Unsubscribe"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "bedrock_policy_attachment" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.bedrock_policy.arn
}

# DynamoDB Table for Chat Sessions
resource "aws_dynamodb_table" "chat_sessions" {
  name         = "${var.project_tag}-ChatSessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"
  range_key    = "message_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "message_id"
    type = "S"
  }

  tags = {
    Name = "${var.project_tag}-chat-sessions"
  }
}

# IAM Policy for DynamoDB access
resource "aws_iam_policy" "dynamodb_policy" {
  name        = "${var.project_tag}-dynamodb-policy"
  description = "Policy for DynamoDB chat sessions table access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = aws_dynamodb_table.chat_sessions.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "dynamodb_policy_attachment" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.dynamodb_policy.arn
}

# Get latest Ubuntu AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# Backend EC2 Instance
resource "aws_instance" "backend" {
  count                  = var.create_vpc ? 1 : 0
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.medium"
  subnet_id              = aws_subnet.public_subnet_01[0].id
  vpc_security_group_ids = [aws_security_group.backend_sg[0].id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  user_data = <<-EOF
              #!/bin/bash
              set -e
              
              # Update system
              apt update
              apt install -y git curl python3 python3-pip python3-venv
              
              # Install Node.js (needed for pm2)
              curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
              apt install -y nodejs
              
              # Clone repository
              cd /opt
              git clone -b aws/main/strands/rag https://github.com/davidawcloudsecurity/learn-lovable-llm.git app
              cd app/server/bedrock
              
              # Create Python virtual environment
              python3 -m venv venv
              source venv/bin/activate
              
              # Install Python dependencies
              pip install --upgrade pip
              pip install -r requirements.txt
              
              # Create .env file
              cat > .env <<ENVFILE
              PORT=8000
              AWS_REGION=us-east-1
              AWS_DEFAULT_REGION=us-east-1
              MODEL_ID=amazon.nova-pro-v1:0
              CHAT_SESSIONS_TABLE_NAME=${aws_dynamodb_table.chat_sessions.name}
              KNOWLEDGE_BASE_ID=
              GUARDRAIL_ID=fake-guardrail-id
              GUARDRAIL_VERSION=
              ENVFILE
              
              # Install PM2 globally
              npm install -g pm2
              
              # Start the FastAPI server with PM2
              PM2_HOME=/etc/.pm2 pm2 start index.py --name bedrock-api --interpreter /opt/app/server/bedrock/venv/bin/python3
              PM2_HOME=/etc/.pm2 pm2 save
              PM2_HOME=/etc/.pm2 pm2 startup systemd -u root --hp /root
              EOF

  tags = {
    Name = "${var.project_tag}-backend"
  }
}

# Frontend EC2 Instance
resource "aws_instance" "frontend" {
  count                  = var.create_vpc ? 1 : 0
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.small"
  subnet_id              = aws_subnet.public_subnet_01[0].id
  vpc_security_group_ids = [aws_security_group.frontend_sg[0].id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  user_data = <<-EOF
              #!/bin/bash
              apt update
              apt install -y nginx git curl
              curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
              apt install -y nodejs
              cd /opt
              git clone -b aws/main/strands/rag https://github.com/davidawcloudsecurity/learn-lovable-llm.git app
              cd app
              npm install
              npm run build
              rm /etc/nginx/sites-enabled/default
              
              # Get backend private IP
              BACKEND_IP="${aws_instance.backend[0].private_ip}"
              
              cat > /etc/nginx/sites-available/app <<NGINX
              server {
                listen 80;
                root /opt/app/dist;
                index index.html;
                location /api/ {
                  proxy_pass http://$BACKEND_IP:8000;
                  proxy_http_version 1.1;
                  proxy_set_header Upgrade \$http_upgrade;
                  proxy_set_header Connection 'upgrade';
                  proxy_set_header Host \$host;
                  proxy_cache_bypass \$http_upgrade;
                  
                  # Increase timeouts for slow LLM responses
                  proxy_read_timeout 300s;      # 5 minutes
                  proxy_connect_timeout 75s;
                  proxy_send_timeout 300s;
                  
                  # Important for streaming
                  proxy_buffering off;
                  proxy_cache off;
                }
                location / {
                  try_files \$uri /index.html;
                }
              }
              NGINX
              ln -s /etc/nginx/sites-available/app /etc/nginx/sites-enabled/
              systemctl restart nginx
              curl -fsSL https://ollama.com/install.sh | sh
              ollama run smollm:1.7b
              EOF

  tags = {
    Name = "${var.project_tag}-frontend"
  }
}

# Application Load Balancer
resource "aws_lb" "frontend" {
  count              = var.create_vpc ? 1 : 0
  name               = "${var.project_tag}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg[0].id]
  subnets            = aws_subnet.public_subnet_01[*].id

  tags = {
    Name = "${var.project_tag}-alb"
  }
}

# Target Group for Frontend EC2
resource "aws_lb_target_group" "frontend" {
  count    = var.create_vpc ? 1 : 0
  name     = "${var.project_tag}-frontend-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.demo_main_vpc[0].id

  health_check {
    path                = "/"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = {
    Name = "${var.project_tag}-frontend-tg"
  }
}

# Register Frontend EC2 with Target Group
resource "aws_lb_target_group_attachment" "frontend" {
  count            = var.create_vpc ? 1 : 0
  target_group_arn = aws_lb_target_group.frontend[0].arn
  target_id        = aws_instance.frontend[0].id
  port             = 80
}

# ALB Listener on port 80
resource "aws_lb_listener" "http" {
  count             = var.create_vpc ? 1 : 0
  load_balancer_arn = aws_lb.frontend[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend[0].arn
  }
}

# CloudFront Distribution with ALB as origin
resource "aws_cloudfront_distribution" "main" {
  count   = var.create_vpc ? 1 : 0
  enabled = true
  comment = "${var.project_tag} CloudFront Distribution"

  origin {
    domain_name = aws_lb.frontend[0].dns_name
    origin_id   = "${var.project_tag}-alb-origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "${var.project_tag}-alb-origin"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = true
      headers      = ["Host", "Origin", "Authorization"]

      cookies {
        forward = "all"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # Cache static assets
  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "${var.project_tag}-alb-origin"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000
    compress    = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.project_tag}-cloudfront"
  }
}

# Outputs
output "alb_dns_name" {
  value       = var.create_vpc ? aws_lb.frontend[0].dns_name : null
  description = "ALB DNS name"
}

output "cloudfront_domain_name" {
  value       = var.create_vpc ? aws_cloudfront_distribution.main[0].domain_name : null
  description = "CloudFront distribution domain name"
}

output "cloudfront_distribution_id" {
  value       = var.create_vpc ? aws_cloudfront_distribution.main[0].id : null
  description = "CloudFront distribution ID"
}
