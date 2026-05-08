#!/bin/bash
set -euxo pipefail

# Update OS
apt-get update -y
apt-get upgrade -y

# Install Docker + Compose v2 (official method)
apt-get install -y ca-certificates curl gnupg git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add ubuntu user to docker group
usermod -aG docker ubuntu || true

# Pull and run application
mkdir -p /opt/ai-order-automation
cd /opt/ai-order-automation

# NOTE: replace REPO_URL via Terraform var or just SSH in and `git clone` once.
# Out-of-the-box this script just prepares the host; CD pipeline handles the rest.
echo "Host ready for deploy at $(date)" > /opt/ai-order-automation/.bootstrap-ok
