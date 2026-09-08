#!/usr/bin/env python3
"""Simple chat client for the Dux backend"""

import json
import os
import uuid

import requests

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")
STEP_LABELS = {
    "hypothesize": "thinking about your problem",
    "research_tools": "reading your code",
    "assess": "checking where you have got to",
}


def stream_reply(user_input, conversation_id):
    """Print progress, then Dux's reply as it arrives

    Args:
        user_input: What you typed
        conversation_id: The thread this message belongs to
    """
    response = requests.post(
        f"{SERVER_URL}/generate/stream",
        json={"user_input": user_input, "conversation_id": conversation_id},
        stream=True,
        timeout=(10, None),
    )
    response.raise_for_status()

    speaking = False
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        event = json.loads(line[len("data: "):])
        if event["type"] == "token":
            if not speaking:
                print("Dux: ", end="", flush=True)
                speaking = True
            print(event["text"], end="", flush=True)
        elif not speaking:
            label = STEP_LABELS.get(event["node"])
            if label:
                print(f"  ... {label}", flush=True)
    print()


def main():
    """Run a chat session against the Dux backend"""
    conversation_id = str(uuid.uuid4())
    while True:
        user_input = input("You: ")
        if user_input.lower() in ("quit", "q"):
            print("Goodbye")
            break
        try:
            stream_reply(user_input, conversation_id)
        except requests.RequestException as error:
            print(f"Error: {error}")
        print()


if __name__ == "__main__":
    main()
