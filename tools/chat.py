#!/usr/bin/env python3
"""Simple chat client for the Dux backend"""

import os
import uuid

import requests

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")

def main():
    """Run a chat session against the Dux backend"""
    conversation_id = str(uuid.uuid4())
    while True:
        user_input = input("You: ")
        if user_input.lower() in ("quit", "q"):
            print("Goodbye")
            break
        try:
            response = requests.post(
                f"{SERVER_URL}/generate",
                json={
                    "user_input": user_input,
                    "conversation_id": conversation_id,
                },
                timeout=120,
            )
            data = response.json()
            output = (data.get("output") or data.get("detail")
                      or "Error: No response")
        except requests.RequestException as e:
            output = f"Error: {e}"
        print(f"Dux: {output}\n")

if __name__ == "__main__":
    main()
