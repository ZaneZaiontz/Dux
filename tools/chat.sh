#!/bin/bash

SERVER_URL="${SERVER_URL:-http://localhost:8000}"

while true; do
    read -p "You: " input

    if [[ "$input" == "quit" || "$input" == "q" ]]; then
        echo "Goodbye"
        break
    fi

    response=$(curl -s -X POST "$SERVER_URL/generate" \
        -H "Content-Type: application/json" \
        -d "{\"user_input\": \"$input\"}")

    output=$(echo "$response" | grep -o '"output":"[^"]*"' | cut -d'"' -f4)
    if [ -z "$output" ]; then
        output=$(echo "$response" | grep -o '"detail":"[^"]*"' | cut -d'"' -f4)
    fi
    if [ -z "$output" ]; then
        output="Error: No response"
    fi
    echo "Dux: $output"
    echo
done

