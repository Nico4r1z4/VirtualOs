#!/usr/bin/env bash
# One-time server setup (Ubuntu 24.04). Run as ubuntu via ssh, or as EC2 user-data.
set -euo pipefail

sudo apt-get update -y
sudo apt-get install -y ca-certificates curl

# Docker (official repo)
if ! command -v docker >/dev/null; then
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
    https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo usermod -aG docker ubuntu
fi

mkdir -p ~/virtualos
echo "Server ready. Next: copy deploy/.env to ~/virtualos/deploy/.env and run deploy.sh from your machine."
