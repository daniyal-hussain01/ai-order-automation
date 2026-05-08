variable "project_name" {
  description = "Project identifier — used in resource tags and names."
  type        = string
  default     = "ai-order-automation"
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance size."
  type        = string
  default     = "t3.small"
}

variable "key_name" {
  description = "Existing EC2 key pair name for SSH."
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "CIDRs allowed to SSH. Lock this down in real deployments."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

output "public_ip" {
  description = "Elastic IP of the EC2 instance."
  value       = aws_eip.app.public_ip
}

output "url" {
  description = "Application URL."
  value       = "http://${aws_eip.app.public_ip}"
}

output "ssh_command" {
  description = "Convenience SSH command."
  value       = "ssh -i ~/.ssh/${var.key_name}.pem ubuntu@${aws_eip.app.public_ip}"
}
