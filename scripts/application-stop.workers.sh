#!/bin/bash

set -e

echo "Stopping running containers..."
sudo docker compose -f /home/ubuntu/g6_arquisis_back/docker-compose.workers.yml down || true

echo "Removing old deployment files..."
sudo rm -f /home/ubuntu/g6_arquisis_back/docker-compose.workers.yml
sudo rm -rf /home/ubuntu/g6_arquisis_back/scripts

echo "Cleanup done."