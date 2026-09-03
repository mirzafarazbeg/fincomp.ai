#!/usr/bin/env bash
# System-level setup for running ComplianceGPT Phase 1 on Google Colab.
# Colab has no Docker daemon, so this installs Postgres+pgvector and Ollama
# directly instead of using docker-compose.yml (that file is for a real
# on-prem/cloud box later). Run once per Colab session (state doesn't
# survive a runtime restart).
#
# Usage (in a Colab cell):
#   !bash scripts/colab_setup.sh
set -euo pipefail

echo "== Installing Postgres 16 + pgvector + poppler-utils =="
apt-get update -qq
apt-get install -y -qq postgresql-16 postgresql-16-pgvector poppler-utils

echo "== Starting Postgres =="
service postgresql start
sleep 2

echo "== Creating compliancegpt role/db =="
su postgres -c "psql -c \"CREATE USER compliancegpt WITH PASSWORD 'devpassword' SUPERUSER;\"" || true
su postgres -c "psql -c \"CREATE DATABASE compliancegpt OWNER compliancegpt;\"" || true
PGPASSWORD=devpassword psql -h localhost -U compliancegpt -d compliancegpt -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "== Installing Ollama (will use the Colab GPU automatically) =="
curl -fsSL https://ollama.com/install.sh | sh

echo "== Starting Ollama server in the background =="
nohup ollama serve > /tmp/ollama.log 2>&1 &
sleep 3

echo "== Pulling the default model (qwen2.5:7b-instruct-q4_K_M) =="
ollama pull qwen2.5:7b-instruct-q4_K_M

echo "== Installing Python dependencies =="
pip install -q -r requirements.txt

echo ""
echo "Setup done. Next, in a notebook cell:"
echo "  import os"
echo "  os.environ['DATABASE_URL'] = 'postgresql://compliancegpt:devpassword@localhost:5432/compliancegpt'"
echo "  os.environ['OLLAMA_URL'] = 'http://localhost:11434'"
echo "  os.environ['OLLAMA_MODEL'] = 'qwen2.5:7b-instruct-q4_K_M'"
echo "  !python3 -m services.rag.ingest"
echo "  !python3 -m services.rag.eval"
