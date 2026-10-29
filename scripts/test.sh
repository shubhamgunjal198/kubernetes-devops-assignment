#!/bin/bash
set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"

echo "Testing NGINX..."
curl -fsS "$BASE_URL/"
echo

echo "Testing API and PostgreSQL..."
curl -fsS "$BASE_URL/api/health"
echo

echo "Testing web backend..."
curl -fsS "$BASE_URL/web/"
echo

echo "All HTTP smoke tests passed."
