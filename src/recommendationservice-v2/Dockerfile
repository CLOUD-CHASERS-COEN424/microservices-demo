# Copyright 2026 Concordia University COEN 424 / COEN 6313 Project
# Dockerfile for RecommendationService v2 (AI Agent with Gemini Tool-Calling & Cloud Firestore)

ARG BUILDPLATFORM=linux/amd64
FROM --platform=$BUILDPLATFORM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM --platform=$BUILDPLATFORM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /recommendationservice

COPY --from=builder /install /usr/local
COPY . .

# Run as non-root user (UID 1000) to match Kubernetes securityContext
RUN useradd -u 1000 -m appuser && chown -R 1000:1000 /recommendationservice
USER 1000

ENV PORT="8080"
ENV HTTP_PORT="8081"
EXPOSE 8080 8081

ENTRYPOINT ["python", "recommendation_server.py"]
