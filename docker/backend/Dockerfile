# Dockerfile for building the backend

FROM python:3.13-slim

RUN apt update && apt install -y curl

COPY requirements.txt /

RUN pip install --no-cache-dir -r /requirements.txt
