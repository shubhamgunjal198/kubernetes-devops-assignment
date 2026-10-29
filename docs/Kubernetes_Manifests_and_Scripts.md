# Kubernetes DevOps Assignment: Manifests and Scripts

This file is a GitHub-friendly reference for the Kubernetes YAML manifests and helper scripts used by this assessment. It explains what each file does and includes its contents for easy review.

> **Important:** The individual files under `k8s/` and `scripts/` remain the files used by the deployment. This document is a readable reference copy. If you change a manifest or script, update this document too so they stay in sync. The credentials shown in the PostgreSQL manifest are for local assessment use only and must not be used in production.

## Project resource order

1. `k8s/namespace.yaml` — create the namespace.
2. `k8s/storage.yaml` — create the StorageClass, PersistentVolume (PV), and PersistentVolumeClaim (PVC).
3. `k8s/postgres.yaml` — create the demo Secret, PostgreSQL Deployment, and PostgreSQL Service.
4. `k8s/app.yaml` — create the Notes API and web backend Deployments and Services.
5. `k8s/nginx.yaml` — create the NGINX ConfigMap, Deployment, and Service.

The deployment script `scripts/deploy.sh` runs these steps in dependency order and prints a resource summary. After deployment, start port-forwarding in one Terminal window and run `scripts/test.sh` in another. Use `scripts/test-persistence.sh` to perform the database persistence check.

## 1. `k8s/namespace.yaml`

**Purpose:** Creates the `devops-assignment` namespace, which groups the application's Kubernetes resources.

**Apply command:**

```bash
kubectl apply -f k8s/namespace.yaml
kubectl get namespaces
```

**Manifest:**

```yaml

apiVersion: v1
kind: Namespace
metadata:
  name: devops-assignment

```

## 2. `k8s/storage.yaml`

**Purpose:** Defines the `postgres-local` StorageClass, a 1 GiB PersistentVolume named `postgres-pv`, and the `postgres-pvc` claim used by PostgreSQL. The `hostPath` is inside the Kubernetes node filesystem, which in Docker Desktop may be a VM/container filesystem rather than a direct macOS folder. This is a local learning setup, not a production storage design.

**Apply and verify:**

```bash
kubectl apply -f k8s/storage.yaml
kubectl get storageclass
kubectl get pv
kubectl get pvc -n devops-assignment
kubectl describe pvc postgres-pvc -n devops-assignment
```

**Manifest:**

```yaml

apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: postgres-local
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: postgres-pv
spec:
  capacity:
    storage: 1Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: postgres-local
  hostPath:
    path: /mnt/data/postgres
    type: DirectoryOrCreate
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: devops-assignment
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: postgres-local
  resources:
    requests:
      storage: 1Gi

```

## 3. `k8s/postgres.yaml`

**Purpose:** Creates the demo-only PostgreSQL Secret, a single-replica PostgreSQL 16 Deployment, and the internal `postgres` Service on port 5432. The Pod uses `nodeSelector: workload: database` and mounts the `postgres-pvc` claim. The init container prepares the hostPath directory permissions in this local learning environment.

**Prerequisite:** The namespace and storage should already be applied, and the node must have the label `workload=database`. `scripts/deploy.sh` performs the node label and resource ordering automatically.

**Apply and verify:**

```bash
kubectl apply -f k8s/postgres.yaml
kubectl rollout status deployment/postgres -n devops-assignment --timeout=240s
kubectl get pods -n devops-assignment -o wide
kubectl logs deployment/postgres -n devops-assignment
kubectl get pvc -n devops-assignment
```

**Manifest:**

```yaml

apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: devops-assignment
type: Opaque
stringData:
  # Demo-only local assessment values. Replace for any non-demo environment.
  POSTGRES_DB: notesdb
  POSTGRES_USER: appuser
  POSTGRES_PASSWORD: local-dev-password-change-me
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: devops-assignment
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      nodeSelector:
        workload: database
      # hostPath directories may be root-owned on a local development node.
      # Set volume ownership for this learning environment before PostgreSQL starts.
      initContainers:
        - name: set-data-permissions
          image: busybox:1.36
          command: ["sh", "-c", "mkdir -p /data/pgdata && chown -R 999:999 /data"]
          securityContext:
            runAsUser: 0
          volumeMounts:
            - name: postgres-data
              mountPath: /data
      containers:
        - name: postgres
          image: postgres:16
          imagePullPolicy: IfNotPresent
          ports:
            - name: postgres
              containerPort: 5432
          env:
            - name: POSTGRES_DB
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_DB
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_USER
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_PASSWORD
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
          readinessProbe:
            exec:
              command:
                - sh
                - -c
                - pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
            initialDelaySeconds: 10
            periodSeconds: 5
            timeoutSeconds: 3
          livenessProbe:
            exec:
              command:
                - sh
                - -c
                - pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 3
      volumes:
        - name: postgres-data
          persistentVolumeClaim:
            claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: devops-assignment
spec:
  type: ClusterIP
  selector:
    app: postgres
  ports:
    - name: postgres
      port: 5432
      targetPort: 5432

```

## 4. `k8s/app.yaml`

**Purpose:** Creates the Flask Notes API Deployment and Service (`notes-api` / `api-service`) on port 5000, plus the lightweight HTTP echo web backend and Service (`web-backend` / `web-service`) on port 5678. The API receives database connection settings from `postgres-secret`.

**Prerequisite:** Build the API image first, and make sure it is available to Docker Desktop Kubernetes.

**Build, apply, and verify:**

```bash
docker build -t devops-notes-api:1.0 ./app
kubectl apply -f k8s/app.yaml
kubectl rollout status deployment/notes-api -n devops-assignment --timeout=240s
kubectl rollout status deployment/web-backend -n devops-assignment --timeout=240s
kubectl get deployments,services -n devops-assignment
```

**Manifest:**

```yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: notes-api
  namespace: devops-assignment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: notes-api
  template:
    metadata:
      labels:
        app: notes-api
    spec:
      containers:
        - name: notes-api
          image: devops-notes-api:1.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 5000
          env:
            - name: DB_HOST
              value: postgres
            - name: DB_PORT
              value: "5432"
            - name: DB_NAME
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_DB
            - name: DB_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_USER
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_PASSWORD
          readinessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 4
          livenessProbe:
            tcpSocket:
              port: 5000
            initialDelaySeconds: 20
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: api-service
  namespace: devops-assignment
spec:
  type: ClusterIP
  selector:
    app: notes-api
  ports:
    - name: http
      port: 5000
      targetPort: 5000
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-backend
  namespace: devops-assignment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web-backend
  template:
    metadata:
      labels:
        app: web-backend
    spec:
      containers:
        - name: web-backend
          image: hashicorp/http-echo:1.0.0
          args:
            - "-listen=:5678"
            - "-text=Web backend is working"
          ports:
            - name: http
              containerPort: 5678
---
apiVersion: v1
kind: Service
metadata:
  name: web-service
  namespace: devops-assignment
spec:
  type: ClusterIP
  selector:
    app: web-backend
  ports:
    - name: http
      port: 5678
      targetPort: 5678

```

## 5. `k8s/nginx.yaml`

**Purpose:** Creates a ConfigMap with the NGINX reverse-proxy configuration, the `nginx-proxy` Deployment, and an internal Service on port 80.

- `/` returns a simple response directly from NGINX.
- `/api/` routes to `api-service:5000`. The trailing slash in `proxy_pass` removes the `/api/` prefix before the request reaches Flask.
- `/web/` routes to `web-service:5678`.

**Apply and verify:**

```bash
kubectl apply -f k8s/nginx.yaml
kubectl rollout status deployment/nginx-proxy -n devops-assignment --timeout=240s
kubectl get pods,services -n devops-assignment
```

**Manifest:**

```yaml

apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-config
  namespace: devops-assignment
data:
  default.conf: |
    server {
        listen 80;
        server_name _;

        location = / {
            default_type text/plain;
            return 200 "Kubernetes DevOps Assignment - NGINX is working\n";
        }

        location /api/ {
            proxy_pass http://api-service:5000/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /web/ {
            proxy_pass http://web-service:5678/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
    }
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-proxy
  namespace: devops-assignment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-proxy
  template:
    metadata:
      labels:
        app: nginx-proxy
    spec:
      containers:
        - name: nginx
          image: nginx:1.28-alpine
          ports:
            - name: http
              containerPort: 80
          volumeMounts:
            - name: nginx-config
              mountPath: /etc/nginx/conf.d/default.conf
              subPath: default.conf
              readOnly: true
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 3
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 10
            periodSeconds: 10
      volumes:
        - name: nginx-config
          configMap:
            name: nginx-config
---
apiVersion: v1
kind: Service
metadata:
  name: nginx-proxy
  namespace: devops-assignment
spec:
  type: ClusterIP
  selector:
    app: nginx-proxy
  ports:
    - name: http
      port: 80
      targetPort: 80

```

## 6. `scripts/deploy.sh`

**Purpose:** Automates the deployment steps: checks Docker and `kubectl`, labels the Kubernetes node, builds the API image, applies manifests in order, waits for Deployments, and prints Pods, Services, PVs and PVCs.

**Run it from the project directory:**

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

**Script:**

```bash

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="devops-assignment"
API_IMAGE="devops-notes-api:1.0"

cd "$ROOT_DIR"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "ERROR: kubectl is not installed or not on PATH." >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not on PATH." >&2
  exit 1
fi

echo "[1/7] Checking the Kubernetes cluster..."
kubectl get nodes
NODE="$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')"
if [[ -z "$NODE" ]]; then
  echo "ERROR: No Kubernetes node was found. Start Docker Desktop Kubernetes." >&2
  exit 1
fi
kubectl label nodes "$NODE" workload=database --overwrite

echo "[2/7] Building the Flask API image: $API_IMAGE"
docker build -t "$API_IMAGE" ./app

echo "[3/7] Creating the namespace..."
kubectl apply -f k8s/namespace.yaml

echo "[4/7] Applying persistent storage..."
kubectl apply -f k8s/storage.yaml

# A locally built Docker image may be shared directly with Docker Desktop Kubernetes.
# If a Pod reports ImagePullBackOff, inspect events and confirm the image is visible to the cluster.
echo "[5/7] Deploying PostgreSQL..."
kubectl apply -f k8s/postgres.yaml
kubectl rollout status deployment/postgres -n "$NAMESPACE" --timeout=240s

echo "[6/7] Deploying the API, web backend, and NGINX..."
kubectl apply -f k8s/app.yaml
kubectl rollout status deployment/notes-api -n "$NAMESPACE" --timeout=240s
kubectl rollout status deployment/web-backend -n "$NAMESPACE" --timeout=240s
kubectl apply -f k8s/nginx.yaml
kubectl rollout status deployment/nginx-proxy -n "$NAMESPACE" --timeout=240s

echo "[7/7] Deployment summary"
kubectl get pods,services -n "$NAMESPACE"
kubectl get pv
kubectl get pvc -n "$NAMESPACE"

echo
echo "Deployment manifests applied. In a separate Terminal window, run:"
echo "  kubectl port-forward svc/nginx-proxy 8080:80 -n $NAMESPACE"
echo "Then run: ./scripts/test.sh"

```

## 7. `scripts/test.sh`

**Purpose:** Performs basic HTTP smoke tests for the NGINX root route, the API health/database connectivity endpoint, the web backend route, and the notes list endpoint. The script uses `curl` and stops if a request fails.

**Usage:** Start the port-forward in a separate Terminal window and keep it running:

```bash
kubectl port-forward svc/nginx-proxy 8080:80 -n devops-assignment
```

Then run in the project folder:

```bash
chmod +x scripts/test.sh
./scripts/test.sh
```

**Script:**

```bash

#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"

for command_name in curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "ERROR: $command_name is required." >&2
    exit 1
  fi
done

request() {
  local description="$1"
  shift
  echo "== $description =="
  curl --fail --silent --show-error "$@"
  echo
echo
}

request "NGINX root route" "$BASE_URL/"
request "API health and database connectivity" "$BASE_URL/api/health"
request "Web backend route" "$BASE_URL/web/"
request "List notes API" "$BASE_URL/api/notes"

echo "Basic HTTP smoke tests passed."
echo "Note: this does not by itself prove data persistence; use scripts/test-persistence.sh for that check."

```

## 8. `scripts/test-persistence.sh`

**Purpose:** Creates a uniquely named note, confirms it is returned by the API, deletes only the PostgreSQL Pod, waits for its replacement, then checks that the same note still exists and displays PVC status. **Do not delete the PVC or PV during this test.**

**Prerequisites:** The project is deployed and the port-forward is active. `kubectl` and `curl` must be available. This test deletes the current PostgreSQL Pod; run it only in the intended assessment environment.

**Run:**

```bash
chmod +x scripts/test-persistence.sh
./scripts/test-persistence.sh
```

**Script:**

```bash

#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
NAMESPACE="devops-assignment"
NOTE_CONTENT="persistence-check-$(date +%s)"

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required." >&2
  exit 1
fi

# Add a unique row and confirm it can be read before replacing the database Pod.
echo "Creating a test note..."
curl --fail --silent --show-error -X POST "$BASE_URL/api/notes" \
  -H 'Content-Type: application/json' \
  -d "{\"content\":\"$NOTE_CONTENT\"}"
echo

echo "Confirming the note exists before Pod recreation..."
BEFORE="$(curl --fail --silent --show-error "$BASE_URL/api/notes")"
printf '%s\n' "$BEFORE"
if ! printf '%s' "$BEFORE" | grep -Fq "$NOTE_CONTENT"; then
  echo "ERROR: The new note was not found before the persistence test." >&2
  exit 1
fi

echo
echo "Deleting only the PostgreSQL Pod. Do NOT delete the PVC or PV."
kubectl delete pod -n "$NAMESPACE" -l app=postgres
kubectl rollout status deployment/postgres -n "$NAMESPACE" --timeout=240s

echo "Checking storage claim and replacement Pod..."
kubectl get pods -n "$NAMESPACE" -o wide
kubectl get pvc -n "$NAMESPACE"

echo "Confirming the same note exists after Pod recreation..."
AFTER="$(curl --fail --silent --show-error "$BASE_URL/api/notes")"
printf '%s\n' "$AFTER"
if ! printf '%s' "$AFTER" | grep -Fq "$NOTE_CONTENT"; then
  echo "ERROR: Note was not found after PostgreSQL Pod recreation." >&2
  exit 1
fi

echo
echo "Persistence check passed: the note remained after PostgreSQL Pod recreation."

```

## 9. Useful verification commands

```bash
# Confirm Kubernetes context and node status
kubectl config current-context
kubectl get nodes --show-labels

# Review application resources
kubectl get pods,deployments,services -n devops-assignment -o wide

# Review storage
kubectl get storageclass
kubectl get pv
kubectl get pvc -n devops-assignment

# Check logs or describe a workload if something is failing
kubectl logs deployment/postgres -n devops-assignment
kubectl describe pods -n devops-assignment

# Check HTTP routes (requires the port-forward to be running)
curl -i http://localhost:8080/
curl -i http://localhost:8080/api/health
curl -i http://localhost:8080/api/notes
curl -i http://localhost:8080/web/
```

## 10. Notes before assessment submission

- Run the deployment and testing scripts on your own cluster and record the actual output. Do not mark a test PASS based only on the presence of files.
- The local `hostPath` storage and single-node scheduling are suitable for this learning assessment, not a production high-availability design.
- The `postgres-secret` contains demonstration credentials. Do not use real or sensitive credentials in a public GitHub repository.
- Keep this reference document synchronized with the actual files in `k8s/` and `scripts/`.

