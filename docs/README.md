# Kubernetes DevOps Assignment

A local single-node Kubernetes assessment project for a small Notes API, a simple web backend, PostgreSQL storage, and NGINX path-based routing. The target environment is macOS on Apple silicon with Docker Desktop Kubernetes.

> **Assessment honesty:** This repository provides the application code, Kubernetes manifests, deployment scripts, and validation commands. The files were generated as a submission starter and have not been deployed against your Mac's Kubernetes cluster from this environment. Record a test as **PASS** only after you run it and observe the expected result on your machine.

## 1. Architecture

```text
Mac / curl
    |
    | http://localhost:8080 (kubectl port-forward)
    v
NGINX Service + Pod :80
    |-- GET / --------> NGINX responds directly
    |-- /api/* --------> api-service :5000 --> Flask Notes API
    |                                           |
    |                                           v
    |                                    postgres Service :5432
    |                                           |
    |                                           v
    |                                     PostgreSQL Pod
    |                                           |
    |                                           v
    |                                      PVC --> PV
    |
    `-- /web/* --------> web-service :5678 --> HTTP echo backend
```

All application resources are grouped in the `devops-assignment` namespace. PostgreSQL's Deployment uses `nodeSelector: workload: database`; the deployment script adds that label to the single local Kubernetes node.

### Request flow

1. Start a port-forward from local port `8080` to the `nginx-proxy` Service's port `80`.
2. NGINX receives the request and selects a route based on its URL path.
3. `/` returns a plain text message directly from NGINX.
4. `/api/health` is proxied to Flask `/health`; `/api/notes` is proxied to Flask `/notes`. NGINX's trailing-slash `proxy_pass` removes the `/api/` prefix.
5. Flask connects to the PostgreSQL Service named `postgres` on port `5432` to read or write notes.
6. PostgreSQL stores its data in its mounted PVC, which is bound to the PV configured for this local single-node exercise.
7. `/web/` is proxied to the lightweight HTTP echo service.

## 2. Repository structure

```text
app/
  app.py                 Flask API: health, list notes, create note
  requirements.txt       Python application dependencies
  Dockerfile             Builds the API container image
k8s/
  namespace.yaml         Namespace for the assignment
  storage.yaml           StorageClass, PersistentVolume, PersistentVolumeClaim
  postgres.yaml          Demo Secret, PostgreSQL Deployment and Service
  app.yaml               API and web-backend Deployments and Services
  nginx.yaml             NGINX ConfigMap, Deployment and Service
nginx/
  nginx.conf             Standalone copy of NGINX routing configuration
scripts/
  deploy.sh              Build image and apply resources in dependency order
  test.sh                HTTP smoke tests
  test-persistence.sh    Optional controlled database-Pod persistence test
README.md
.gitignore
```

## 3. Tools and why they are used

| Tool or resource | Purpose |
|---|---|
| Docker Desktop | Runs the local Docker engine and Kubernetes cluster; no EC2 instance is required for this local assessment. |
| Dockerfile and image | Package the Flask application and its Python dependencies into a repeatable container image. |
| `kubectl` | Applies manifests and inspects cluster resources, rollouts, logs, and storage. |
| Namespace | Groups assignment resources under `devops-assignment`. |
| Deployment | Declares the desired Pod count and recreates Pods when they are removed or fail. |
| Service | Provides stable in-cluster networking names for API, web, database, and NGINX components. |
| NGINX + ConfigMap | Offers one HTTP entry point and routes by path while keeping its config outside the image. |
| PostgreSQL | Stores notes in a relational database. |
| StorageClass, PV, PVC | Define available storage and the claim mounted by PostgreSQL. |
| Node label + `nodeSelector` | Demonstrate placement of the PostgreSQL Pod onto a matching node. |
| Git/GitHub | Track and submit source files, manifests, scripts, and documentation. |

## 4. Prerequisites

- Docker Desktop for Mac with Apple silicon, running with Kubernetes enabled.
- `kubectl`, Git, and a shell (the steps below use macOS zsh/Bash).
- The current Kubernetes context points to your local Docker Desktop cluster.

Check the environment:

```bash
docker --version
docker info
kubectl version --client
git --version
kubectl config current-context
kubectl get nodes
kubectl get pods -A
```

Before deployment, `kubectl get nodes` should show a node in `Ready` state. If Docker Desktop's Kubernetes environment is not running, start it first.

## 5. Deploy the application

Run commands from the project root. The deployment script labels the first node, builds the API image, then applies Kubernetes resources in dependency order.

```bash
chmod +x scripts/deploy.sh scripts/test.sh scripts/test-persistence.sh
./scripts/deploy.sh
```

The script applies:

1. `k8s/namespace.yaml`
2. `k8s/storage.yaml`
3. `k8s/postgres.yaml`, then waits for the PostgreSQL rollout
4. `k8s/app.yaml`, then waits for the API and web backend rollouts
5. `k8s/nginx.yaml`, then waits for the NGINX rollout

The API image is named `devops-notes-api:1.0`. Docker Desktop Kubernetes usually integrates with its local image environment, but details can vary by version. If the API Pod reports `ImagePullBackOff`, inspect Pod events and confirm that the Kubernetes runtime can access the built image.

## 6. Storage configuration

`k8s/storage.yaml` defines:

- StorageClass: `postgres-local`, using `kubernetes.io/no-provisioner`.
- PersistentVolume: `postgres-pv`, capacity `1Gi`, `ReadWriteOnce`, and host path `/mnt/data/postgres` inside the Kubernetes node.
- PersistentVolumeClaim: `postgres-pvc`, requesting `1Gi` in namespace `devops-assignment`.

The PostgreSQL Deployment mounts the PVC at `/var/lib/postgresql/data` and sets `PGDATA` to `/var/lib/postgresql/data/pgdata`. An init container sets ownership for the local assessment volume before PostgreSQL starts.

Check storage status:

```bash
kubectl get storageclass
kubectl get pv
kubectl get pvc -n devops-assignment
kubectl describe pvc postgres-pvc -n devops-assignment
```

Expected after a successful bind: `postgres-pvc` shows `Bound` and is connected to `postgres-pv`.

**Storage limitation:** `hostPath` is a local learning configuration. The path is on the Kubernetes node's filesystem, which may be a Linux VM or container environment, not a normal macOS folder. It is not a production storage or backup solution and may not survive deleting/recreating the entire cluster. The PV reclaim policy is `Retain`, so cleanup may require manual work.

## 7. Networking flow and access

Open a second Terminal window and keep this command running:

```bash
kubectl port-forward svc/nginx-proxy 8080:80 -n devops-assignment
```

Use another Terminal window for tests:

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/api/health
curl -i http://localhost:8080/api/notes
curl -i http://localhost:8080/web/
```

Route reference:

| Local URL | Destination | Expected behavior |
|---|---|---|
| `/` | NGINX itself | Plain text NGINX message |
| `/api/health` | Flask `/health` | JSON status; database should be connected |
| `/api/notes` | Flask `/notes` | JSON array of saved notes |
| `POST /api/notes` | Flask `/notes` | Creates a note and returns HTTP 201 |
| `/web/` | HTTP echo backend | `Web backend is working` |

Create a note:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"content":"Kubernetes assessment test note"}'
```

Then list saved notes:

```bash
curl -i http://localhost:8080/api/notes
```

## 8. Validation and testing

### Test commands

After deployment and while the port-forward is running:

```bash
./scripts/test.sh
```

This checks NGINX's root, database-aware API health endpoint, web backend route, and listing notes. The script stops when a `curl` request fails.

To test persistence, first make sure the application is healthy and that any important data is backed up. Then run:

```bash
./scripts/test-persistence.sh
```

The optional persistence script adds a uniquely named note, deletes **only** the PostgreSQL Pod, waits for the Deployment to recreate it, checks the PVC, and confirms that the same note can still be read. Do not delete the PVC or PV during this test.

### Record your observed results before submission

The source bundle cannot truthfully claim that the workload was run on your Mac. Complete this checklist after running the tests:

- [ ] `kubectl get nodes` — node is `Ready`.
- [ ] `kubectl get pods -n devops-assignment -o wide` — expected application Pods are `Running` and ready.
- [ ] `kubectl get services -n devops-assignment` — expected Services exist.
- [ ] `kubectl get pvc -n devops-assignment` — `postgres-pvc` is `Bound`.
- [ ] `curl http://localhost:8080/` — NGINX response received.
- [ ] `curl http://localhost:8080/api/health` — API returns healthy JSON and database connected.
- [ ] `curl http://localhost:8080/web/` — web backend response received.
- [ ] POST then GET `/api/notes` — the new note appears in the API result.
- [ ] `scripts/test-persistence.sh` — the note remains after PostgreSQL Pod recreation.

For troubleshooting, collect these outputs:

```bash
kubectl get pods,services -n devops-assignment
kubectl get pv
kubectl get pvc -n devops-assignment
kubectl describe pod -n devops-assignment <pod-name>
kubectl logs -n devops-assignment deployment/notes-api
kubectl logs -n devops-assignment deployment/postgres
kubectl logs -n devops-assignment deployment/nginx-proxy
```

## 9. Common problems

- **Node not `Ready`:** Start Docker Desktop Kubernetes and verify `kubectl config current-context`.
- **API Pod `ImagePullBackOff`:** Inspect `kubectl describe pod`; confirm `devops-notes-api:1.0` is visible to the Kubernetes runtime.
- **PVC remains `Pending`:** Check events with `kubectl describe pvc postgres-pvc -n devops-assignment`; confirm the PV capacity, access mode, and StorageClass match the claim.
- **API returns 503:** Check PostgreSQL Pod readiness, Secret references, API logs, and PVC status.
- **NGINX returns 502:** Check the API/web Pods and Services, their ports and labels, and the NGINX ConfigMap.
- **Note vanishes in persistence test:** Stop and investigate before claiming success; verify that PostgreSQL uses `postgres-pvc` and is writing under the mounted path.

## 10. Demo credentials and security

The `postgres-secret` in `k8s/postgres.yaml` contains an intentionally obvious **demo-only** password so this local assessment can be deployed from the files. Do not reuse it outside this learning environment. Kubernetes Secret `stringData` is convenient for configuration, but committing secret manifests to a public production repository is not a secure secret-management pattern. For real systems, use a secret manager, restrict RBAC, enable suitable encryption at rest, and avoid committing sensitive values.

## 11. Save and push to GitHub

```bash
git status
git add README.md app k8s nginx scripts .gitignore
git commit -m "Submit Kubernetes DevOps assessment"
git push
```

Add the PowerPoint or architecture guide under `docs/` only if supporting documentation is useful for your assessment. Do not commit screenshots containing personal information, real credentials, or tokens.

## 12. Submission summary

This submission includes the Flask API source, Dockerfile, Python dependencies, five Kubernetes manifest files, an NGINX configuration, a repeatable deployment script, HTTP smoke tests, a persistence test, `.gitignore`, and this README. Run it in your own Docker Desktop Kubernetes environment and record the real validation results before submitting.
