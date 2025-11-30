#!/bin/bash

echo "Pulling aplication"
cd /home/ubuntu/g6_arquisis_back
docker-compose --file docker-compose.production.yml pull