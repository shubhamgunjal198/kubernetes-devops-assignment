# Kubernetes Configuration Reference

This reference describes the resources in the project guide. Use it as a design map and verify that the manifests in your working tree contain the same names, labels, ports, and paths.

## Resource map

| File | Expected resources | Role |
|---|---|---|
| `k8s/namespace.yaml` | Namespace `devops-assignment` | Groups the application resources. |
| `k8s/storage.yaml` | StorageClass `postgres-local`, PV `postgres-pv`, PVC `postgres-pvc` | Requests and supplies persistent storage for PostgreSQL. |
| `k8s/postgres.yaml` | Secret `postgres-secret`, Deployment `postgres`, Service `postgres` | Runs PostgreSQL and exposes it internally on port 5432. |
| `k8s/app.yaml` | Deployment `notes-api`, Service `api-service`, Deployment `web-backend`, Service `web-service` | Runs the Flask notes API and simple HTTP echo backend. |
| `k8s/nginx.yaml` | ConfigMap `nginx-config`, Deployment `nginx-proxy`, Service `nginx-proxy` | Configures and exposes NGINX inside the cluster. |
| `nginx/nginx.conf` | NGINX server configuration | Human-readable copy of the proxy routes; keep in sync with the ConfigMap content. |

## Namespaces and naming

- Namespace: `devops-assignment`
- Node label: `workload=database`
- PostgreSQL: Deployment `postgres`, Service `postgres`, PVC `postgres-pvc`
- API: Deployment `notes-api`, Service `api-service`, container port 5000
- Web backend: Deployment `web-backend`, Service `web-service`, container port 5678
- NGINX: Deployment and Service `nginx-proxy`, container/service port 80

Kubernetes Service names provide stable in-cluster destinations. Pods may be recreated and receive new Pod IP addresses, so callers should use Service names rather than hard-coded Pod IPs.

## Storage design

The learning design uses:

- StorageClass: `postgres-local`, provisioner `kubernetes.io/no-provisioner`, binding mode `Immediate`, reclaim policy `Retain`.
- PersistentVolume: `postgres-pv`, capacity `1Gi`, access mode `ReadWriteOnce`, storage class `postgres-local`, `hostPath` `/mnt/data/postgres` with `DirectoryOrCreate`.
- PersistentVolumeClaim: `postgres-pvc` in namespace `devops-assignment`, requesting `1Gi` with access mode `ReadWriteOnce` and StorageClass `postgres-local`.
- PostgreSQL mounts the PVC at `/var/lib/postgresql/data` and sets `PGDATA` to `/var/lib/postgresql/data/pgdata` in the documented example.

**Important limitation:** a `hostPath` volume belongs to the Kubernetes node's filesystem, which may be a VM/container filesystem rather than the macOS host filesystem. This is suitable for a single-node learning exercise, not a portable or production storage design. A `Retain` policy also means retained data or PV cleanup may require manual handling.

## Node scheduling

The documented workflow labels one node with:

```bash
NODE=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
kubectl label nodes "$NODE" workload=database --overwrite
```

The PostgreSQL Pod template includes:

```yaml
nodeSelector:
  workload: database
```

This tells the scheduler that PostgreSQL must run on a node with that label. Verify placement with:

```bash
kubectl get nodes --show-labels
kubectl get pods -n devops-assignment -o wide
kubectl describe pod -n devops-assignment -l app=postgres
```

On a single-node cluster, this demonstrates selector-based placement only. It does not prove distribution across nodes or high availability.

## Application and database configuration

The documented design uses a Kubernetes Secret named `postgres-secret` with keys `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`. The PostgreSQL Deployment reads these keys into its environment. The API reads the same database values and uses `DB_HOST=postgres` and port 5432 (the default for PostgreSQL).

The API code defines `GET /health`, `GET /notes`, and `POST /notes`. When the NGINX config strips `/api/` from the proxy path, the external routes are `GET /api/health`, `GET /api/notes`, and `POST /api/notes`.

Security note: Kubernetes Secret values in a basic manifest are not encrypted merely because they are under a Secret resource. Use demo-only credentials and keep private values out of Git history.

## NGINX routing

The documented routes are:

| External path | Internal destination | Purpose |
|---|---|---|
| `/` | NGINX response | Confirms the reverse proxy entry point is reachable. |
| `/api/*` | `api-service:5000` | Routes API calls to Flask; the `/api/` prefix is removed by the documented trailing-slash `proxy_pass`. |
| `/web/*` | `web-service:5678` | Routes requests to the HTTP echo backend. |

The exact behavior depends on the `location` blocks and `proxy_pass` values in `nginx/nginx.conf` and the `default.conf` value in ConfigMap `nginx-config`. Keep those copies synchronized; the configuration embedded in `k8s/nginx.yaml` must be complete.

## Useful inspection commands

```bash
kubectl get all -n devops-assignment
kubectl get deployments -n devops-assignment
kubectl get services -n devops-assignment
kubectl get configmap nginx-config -n devops-assignment -o yaml
kubectl get secret postgres-secret -n devops-assignment
kubectl get pv
kubectl get pvc -n devops-assignment
kubectl get pods -n devops-assignment -o wide
```

Avoid displaying decoded Secret values in shared screenshots or logs.
