# Output the public IP of the frontend instance
output "frontend_public_ip" {
  description = "Public IP address of the frontend EC2 instance"
  value       = var.create_vpc ? aws_instance.frontend[0].public_ip : null
}

# Output the public IP of the backend instance
output "backend_public_ip" {
  description = "Public IP address of the backend EC2 instance"
  value       = var.create_vpc ? aws_instance.backend[0].public_ip : null
}

# Output the VPC ID
output "vpc_id" {
  description = "ID of the VPC"
  value       = var.create_vpc ? aws_vpc.demo_main_vpc[0].id : data.aws_vpc.existing[0].id
}

# Output the DynamoDB table name
output "dynamodb_table_name" {
  description = "Name of the DynamoDB chat sessions table"
  value       = aws_dynamodb_table.chat_sessions.name
}

# Output the DynamoDB table ARN
output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB chat sessions table"
  value       = aws_dynamodb_table.chat_sessions.arn
}

# Output the IAM role name
output "ec2_iam_role_name" {
  description = "Name of the IAM role attached to EC2 instances"
  value       = aws_iam_role.ec2_role.name
}

# Output the IAM role ARN
output "ec2_iam_role_arn" {
  description = "ARN of the IAM role attached to EC2 instances"
  value       = aws_iam_role.ec2_role.arn
}

# Output connection instructions
output "connection_instructions" {
  description = "Instructions for connecting to the application"
  value = var.create_vpc ? <<-EOT
    
    Frontend URL: http://${aws_instance.frontend[0].public_ip}
    Backend API: http://${aws_instance.backend[0].public_ip}:8000
    
    SSH to Frontend:
    aws ssm start-session --target ${aws_instance.frontend[0].id}
    
    SSH to Backend:
    aws ssm start-session --target ${aws_instance.backend[0].id}
    
    DynamoDB Table: ${aws_dynamodb_table.chat_sessions.name}
    
    API Endpoints:
    - Health: http://${aws_instance.backend[0].public_ip}:8000/api/health
    - Chat: http://${aws_instance.backend[0].public_ip}:8000/api/chat
    - History: http://${aws_instance.backend[0].public_ip}:8000/api/chat/history
    
  EOT
  : "VPC not created - using existing infrastructure"
}
