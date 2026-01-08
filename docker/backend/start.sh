#!/bin/bash

if [ ! -f .env ]; then
    echo "Error: .env file not found"
    cp env_temp .env
    echo ".env file created"
fi

docker-compose up --build

docker-compose down