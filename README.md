# Secure Enterprise MLOps Pipeline on Kubernetes

A beginner-friendly demonstration of a Python prediction API deployed to Kubernetes, with Kubernetes Secret encryption at rest in etcd and a GitHub Actions build/deploy pipeline.

> **Learning/lab project:** This is a practical security demonstration, not a complete production platform. For production, prefer a managed KMS integration, external secret manager, image scanning/signing, private networking, audit policies, and a tested key-rotation/backup procedure.

## 1. What this project demonstrates

- Build a small Python FastAPI prediction service.
- Package it into a non-root Docker container.
- Create a local Kubernetes cluster using **Kind**.
- Configure the Kubernetes API server to encrypt `Secret` resources with **AES-CBC** before storing them in etcd.
- Inject credentials into the app as environment variables from a Kubernetes Secret.
- Use GitHub Actions to build and push Docker images to Docker Hub.
- Optionally deploy the image to a reachable Kubernetes cluster from GitHub Actions.

## 2. Architecture

```text
Developer pushes code
        |
        v
     GitHub
        |
        v
  GitHub Actions
        |
   Docker build
        |
        v
    Docker Hub
        |
   Kubernetes deploy
        |
        v
  prediction-api Pods
        |
        +---- reads app-credentials Secret
                         |
                  Kubernetes API server
                         |
                 AES-CBC encryption
                         |
                        etcd
                 (ciphertext at rest)
```

### What encryption means here

A Kubernetes Secret's `data` field is Base64-encoded when shown in YAML. Base64 is an encoding, not encryption.

With this project's API-server `EncryptionConfiguration`, the API server encrypts Secret resources before writing them to etcd. When an authorized client requests a Secret, the API server decrypts it before returning it.

The encryption key is stored in a local file for this lab. Protect it carefully. Anyone who obtains both etcd data and the encryption key may be able to recover the stored values. Losing the key can make encrypted data unreadable.

## 3. Prerequisites

Install:

- Docker Desktop
- `kubectl`
- Kind
- Python 3.10+
- Git
- A Docker Hub account
- A GitHub repository

Check tools:

```bash
docker version
kubectl version --client
kind version
python --version
git --version
```

On Windows, run commands in **PowerShell** unless a command is explicitly marked otherwise. Install Kind and kubectl using their official installation instructions if they are missing.

## 4. Project structure

```text
secure-mlops-kubernetes/
├── app/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── encryption/
│   └── (generated encryption-config.yaml; do not commit)
├── kind/
│   └── cluster.yaml
├── k8s/
│   ├── namespace.yaml
│   ├── deployment.yaml
│   └── service.yaml
├── scripts/
│   └── generate-encryption-config.py
├── .github/
│   └── workflows/
│       └── ci-cd.yaml
├── .dockerignore
├── .gitignore
└── README.md
```

## 5. Step 1 — Generate the encryption configuration

From the project root:

```bash
python scripts/generate-encryption-config.py
```

This creates `encryption/encryption-config.yaml` with a fresh random 32-byte AES key.

The generated file is intentionally excluded from Git by `.gitignore`.

**Do not commit this file, paste it into a public repository, or share it in screenshots.** Store a protected backup. For a real production environment, use a KMS provider or an external key-management system and follow its key-rotation guidance.

The important part of the generated configuration looks like this:

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - aescbc:
          keys:
            - name: key1
              secret: BASE64_ENCODED_RANDOM_KEY
      - identity: {}
```

`aescbc` is the encryption provider. `identity` is a fallback for data that was not encrypted by a configured provider; it is not the encryption mechanism. The API server writes new Secret objects using the first provider.

## 6. Step 2 — Create the Kind cluster with encryption enabled

Run this from the project root, after generating the config:

```bash
kind create cluster --name secure-mlops --config kind/cluster.yaml
kubectl cluster-info
kubectl get nodes
```

The Kind configuration mounts the encryption file into the control-plane container and configures the API server with:

```text
--encryption-provider-config=/etc/kubernetes/enc/encryption-config.yaml
```

If cluster creation fails, inspect:

```bash
kind get clusters
docker logs secure-mlops-control-plane
```

If you change the encryption configuration, recreate this disposable lab cluster after protecting any data you need. Do not casually replace encryption keys on a cluster containing important data.

## 7. Step 3 — Create the application Secret

Create a namespace:

```bash
kubectl apply -f k8s/namespace.yaml
```

Create credentials without putting them in a YAML file:

```bash
kubectl create secret generic app-credentials \
  --namespace mlops-demo \
  --from-literal=DB_USERNAME=demo_user \
  --from-literal=DB_PASSWORD='change-this-demo-password' \
  --from-literal=MODEL_API_KEY='demo-api-key'
```

PowerShell users can run the same command on one line:

```powershell
kubectl create secret generic app-credentials --namespace mlops-demo --from-literal=DB_USERNAME=demo_user --from-literal=DB_PASSWORD=change-this-demo-password --from-literal=MODEL_API_KEY=demo-api-key
```

These are dummy lab values. Do not use real credentials in a demo. Avoid putting secrets directly in shell history on a shared machine; for real deployments, use a secret manager or a protected input method.

Confirm the Secret exists without printing its contents:

```bash
kubectl get secret app-credentials -n mlops-demo
```

The Deployment refers to this Secret using `envFrom`. The application only reports whether values are configured; it never returns the values.

## 8. Step 4 — Build and run the API locally (optional)

```bash
cd app
python -m venv .venv
```

Activate the environment:

PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:
```bash
source .venv/bin/activate
```

Install and run:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Try:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

Test prediction:

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"features":[0.2,0.8,0.4]}'
```

Stop the local server and return to the project root before continuing.

## 9. Step 5 — Build and push the Docker image manually

Replace `YOUR_DOCKERHUB_USERNAME` with your Docker Hub username:

```bash
docker build -t YOUR_DOCKERHUB_USERNAME/secure-mlops-api:v1 ./app
docker login
docker push YOUR_DOCKERHUB_USERNAME/secure-mlops-api:v1
```

Update the image in `k8s/deployment.yaml`:

```yaml
image: YOUR_DOCKERHUB_USERNAME/secure-mlops-api:v1
```

For the local Kind cluster, load the locally built image instead of pushing it:

```bash
docker build -t secure-mlops-api:local ./app
kind load docker-image secure-mlops-api:local --name secure-mlops
```

Then set the Deployment image to `secure-mlops-api:local` for the local-only test.

## 10. Step 6 — Deploy to Kubernetes

If using the local image, change the image line in `k8s/deployment.yaml` to:

```yaml
image: secure-mlops-api:local
imagePullPolicy: IfNotPresent
```

Apply resources:

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl get pods -n mlops-demo
kubectl get svc -n mlops-demo
```

Wait for the Pods:

```bash
kubectl rollout status deployment/prediction-api -n mlops-demo
```

Forward the service port:

```bash
kubectl port-forward service/prediction-api 8000:80 -n mlops-demo
```

In another terminal:

```bash
curl http://127.0.0.1:8000/health
```

Test the prediction endpoint:

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"features":[0.2,0.8,0.4]}'
```

Open API documentation at `http://127.0.0.1:8000/docs`.

## 11. Step 7 — Verify encryption in etcd

First, confirm the API server is configured:

```bash
docker exec secure-mlops-control-plane \
  grep -n "encryption-provider-config" /etc/kubernetes/manifests/kube-apiserver.yaml
```

Now inspect the raw etcd value for the Secret. Kind's control-plane container includes `etcdctl` and the local etcd certificates:

```bash
docker exec secure-mlops-control-plane sh -c \
'ETCDCTL_API=3 etcdctl \
 --endpoints=https://127.0.0.1:2379 \
 --cacert=/etc/kubernetes/pki/etcd/ca.crt \
 --cert=/etc/kubernetes/pki/apiserver-etcd-client.crt \
 --key=/etc/kubernetes/pki/apiserver-etcd-client.key \
 get /registry/secrets/mlops-demo/app-credentials' | strings | head
```

Look for a prefix similar to:

```text
k8s:enc:aescbc:v1:key1
```

This prefix indicates that the stored value was encrypted using the configured AES-CBC provider and key name.

Compare that with:

```bash
kubectl get secret app-credentials -n mlops-demo
```

The API server can decrypt the Secret for authorized Kubernetes clients, while the raw etcd record contains encrypted data.

If `strings` is unavailable in the container, save the raw output and inspect it with an available binary-string viewer on your host. Do not publish the raw record or encryption key.

## 12. Step 8 — Configure GitHub Actions CI/CD

Push the project to GitHub:

```bash
git init
git add .
git commit -m "Add secure Kubernetes MLOps pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

In GitHub, open:

**Repository → Settings → Secrets and variables → Actions → New repository secret**

Add:

| Secret name | Value |
|---|---|
| `DOCKERHUB_USERNAME` | Your Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token |

The workflow builds the Docker image and pushes two tags: the commit SHA and `latest`.

### Optional automatic deployment

GitHub-hosted runners cannot normally access your laptop's local Kind cluster. To use the workflow's deploy job, configure a reachable Kubernetes cluster and add a `KUBE_CONFIG` repository secret containing the **Base64-encoded kubeconfig** for a dedicated, least-privilege deployment identity.

For example, on Linux:

```bash
base64 -w 0 ~/.kube/config
```

On PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$HOME\.kube\config"))
```

Copy the output into the GitHub `KUBE_CONFIG` secret.

Important:
- Do not use an administrator kubeconfig for CI/CD.
- The kubeconfig must point to an API endpoint reachable from the GitHub-hosted runner.
- Create `app-credentials` in the target cluster separately before deployment.
- A local Kind cluster on your laptop is not reachable from GitHub-hosted runners by default.
- For a real setup, use a secured self-hosted runner or a managed Kubernetes cluster with a controlled deployment identity.

The workflow's deploy job runs only when the repository variable `DEPLOY_ENABLED` is set to `true`. If you do not configure deployment, leave that variable unset; the build-and-push job still runs.

## 13. Troubleshooting

| Problem | What to check |
|---|---|
| Kind cluster creation fails | Encryption file exists and YAML is valid |
| Pod is `ImagePullBackOff` | Image name, registry access and image tag |
| Pod is `CreateContainerConfigError` | `app-credentials` Secret exists in `mlops-demo` |
| API returns connection error | Port-forward command and Pod status |
| Encryption prefix missing | API-server configuration and whether the Secret was created after encryption was enabled |
| GitHub deploy fails | Kubeconfig endpoint, permissions, Secret and cluster reachability |

Useful commands:

```bash
kubectl get pods -n mlops-demo
kubectl describe pod -n mlops-demo
kubectl logs deployment/prediction-api -n mlops-demo
kubectl get events -n mlops-demo --sort-by=.metadata.creationTimestamp
```

## 14. Cleanup

Delete the lab cluster:

```bash
kind delete cluster --name secure-mlops
```

Remove the generated key only after you no longer need to read data encrypted with it:

```bash
# Linux/macOS
rm encryption/encryption-config.yaml
```

PowerShell:

```powershell
Remove-Item encryption/encryption-config.yaml
```

## 15. Interview explanation

**Q: Why is Base64 not enough for Kubernetes Secrets?**

Base64 is encoding, not encryption. Anyone who can read the stored Secret data can decode it. Encryption at rest protects the Secret data stored in etcd.

**Q: Where does Kubernetes encrypt the Secret?**

The Kubernetes API server encrypts the Secret before persisting it to etcd. Authorized reads are decrypted by the API server.

**Q: What is EncryptionConfiguration?**

It is an API-server configuration that specifies which resources should be encrypted and which encryption providers and keys should be used.

**Q: Why use AES-CBC?**

AES-CBC is a supported Kubernetes encryption provider and is useful for demonstrating encryption at rest. For production, prefer a supported KMS integration where appropriate, with managed key lifecycle and rotation.

**Q: Does encryption at rest protect a Secret from every user?**

No. It protects stored data in etcd. Users or workloads with permission to read the Secret through the Kubernetes API can still obtain its plaintext value. RBAC and workload security remain essential.

**Q: What happens if the encryption key is lost?**

The API server may no longer be able to decrypt data encrypted with that key. Secure backups and a tested key-rotation procedure are essential.

## 16. Resume project description

**Secure Enterprise MLOps Pipeline on Kubernetes**

- Built and containerized a Python FastAPI prediction service using Docker.
- Configured Kubernetes API-server encryption at rest for Secret resources using AES-CBC.
- Deployed application workloads using Kubernetes Deployments, Services, health probes and resource limits.
- Integrated GitHub Actions for automated Docker image build and Docker Hub publishing.
- Validated encryption by inspecting raw etcd records and confirming the `k8s:enc:aescbc` storage prefix.
- Applied container security practices including non-root execution, dropped Linux capabilities and read-only root filesystem.

## 17. Suggested future improvements

1. Replace the demo prediction logic with a trained ML model.
2. Integrate Prometheus and Grafana.
3. Add Helm charts.
4. Use HashiCorp Vault or a cloud KMS.
5. Add Trivy image vulnerability scanning.
6. Add RBAC with a dedicated CI/CD service account.
7. Implement Argo CD for GitOps deployment.

**Your project completion goal:** Be able to explain the complete flow from GitHub commit → Docker image → Kubernetes Pod → Secret → API server encryption → etcd.
