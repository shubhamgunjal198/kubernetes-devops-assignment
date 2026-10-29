#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Checking Kubernetes..."
kubectl get nodes

NODE=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
kubectl label nodes "$NODE" workload=database --overwrite

echo "Building the API image..."
docker build -t devops-notes-api:1.0 ./app

echo "Creating namespace..."
kubectl apply -f k8s/namespace.yaml

echo "Configuring storage..."
kubectl apply -f k8s/storage.yaml

echo "Deploying PostgreSQL..."
kubectl apply -f k8s/postgres.yaml
kubectl rollout status deployment/postgres \
  -n devops-assignment --timeout=180s

echo "Deploying application..."
kubectl apply -f k8s/app.yaml
kubectl rollout status deployment/notes-api \
  -n devops-assignment --timeout=180s
kubectl rollout status deployment/web-backend \
  -n devops-assignment --timeout=180s

echo "Deploying NGINX..."
kubectl apply -f k8s/nginx.yaml
kubectl rollout status deployment/nginx-proxy \
  -n devops-assignment --timeout=180s

echo "Deployment complete."
kubectl get pods,services -n devops-assignment
kubectl get pv,pvc -n devops-assignment
