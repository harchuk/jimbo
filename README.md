# Cluster Rollback MVP

This project provides a minimal prototype for taking Kubernetes resource
snapshots, storing them in a Git repository and rolling back the cluster state.
It includes both a CLI utility and a web interface with a timeline of commits.

## Requirements

* Python 3.8+
* Access to your cluster via a kubeconfig file (no `kubectl` required)
* Access to a local or remote Git repository
* Git installed in the environment (required by GitPython). The provided
  Dockerfile installs it automatically.

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Take a snapshot

```bash
python -m cluster_rollback.snapshot snapshot
```

This stores current cluster resources under `cluster_rollback/snapshots/` and
commits them to the repository.

### Roll back

```bash
python -m cluster_rollback.snapshot rollback <commit-hash>
```

Apply manifests from the chosen commit to the cluster.

### Run the web UI

```bash
python -m cluster_rollback.web.app
```

Open `http://localhost:8000` to view snapshots and trigger rollbacks.

LDAP authentication and detailed resource selection are out of scope for this
MVP but can be added later.

## Deploying to Kubernetes

Use the pre-built Docker image from the GitHub Container Registry:

```bash
docker pull ghcr.io/harchuk/cluster-rollback:latest
```

Apply the following manifest to run the tool in your cluster. A copy is
available under `k8s/deployment.yaml` for convenience:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cluster-rollback
spec:
  replicas: 1
  selector:
    matchLabels:
      app: cluster-rollback
  template:
    metadata:
      labels:
        app: cluster-rollback
    spec:
      containers:
        - name: web
          image: ghcr.io/harchuk/cluster-rollback:latest
          command: ["python", "-m", "cluster_rollback.web.app"]
          ports:
            - containerPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: cluster-rollback
spec:
  selector:
    app: cluster-rollback
  ports:
    - port: 80
      targetPort: 8000
```

Expose the service with an Ingress or a LoadBalancer according to your
environment. Once deployed, access the UI and use the timeline to select the
desired snapshot and roll back with a single click.

## Continuous delivery

Merging changes to the `master` or `main` branch triggers a GitHub Actions workflow that:

1. Bumps the project version and creates a new Git tag.

2. Builds multi-platform Docker images (linux/amd64 and linux/arm64) and pushes them to Docker Hub and the GitHub Container Registry with both the versioned and `latest` tags.

3. Generates release notes from the commit history and publishes a GitHub release.

Docker credentials must be provided via `DOCKER_USERNAME` and `DOCKER_TOKEN` repository secrets for Docker Hub. The built-in `GITHUB_TOKEN` is used for publishing to `ghcr.io` and creating releases.
