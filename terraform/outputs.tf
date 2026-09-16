output "instance_public_ip" {
  value = aws_instance.metering.public_ip
}

output "ecr_repository_url" {
  value = aws_ecr_repository.metering.repository_url
}