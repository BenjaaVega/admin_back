#!/bin/bash

echo "Aplication starting"
cd /home/ubuntu/g6_arquisis_back
docker-compose --file docker-compose.workers.yml up -d