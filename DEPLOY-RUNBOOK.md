# Deploy runbook — k3d + Rancher (demo)

One paste per phase. Every phase ends in a check that either passes or tells you
what broke. Assumes the `ai-demo` cluster and Rancher on :8443 from `CONTAINERIZE.md`.

## Phase 0 — prove the eval harness before you touch the cluster

No LLM and no cluster needed. If either of these is red, stop and fix the dataset.

```powershell
python -m evals.runner --validate   # hidden tests must FAIL on every unfixed seed
python -m evals.runner --selftest 
uv run python -m evals.runner# hidden tests must PASS on every reference solution
```

Expected: `8/8 tasks valid`, then `8/8 tasks solvable`.

## Phase 1 — build and import the image

```powershell
docker build -f docker/Dockerfile -t langgraph-ollama:demo .
k3d image import langgraph-ollama:demo -c ai-demo
```

Check: `docker images langgraph-ollama:demo` shows the tag; import prints `Successfully imported`.

## Phase 2 — deploy

```powershell
kubectl apply -k k8s/
kubectl -n ai-apps rollout status deployment/langgraph-streamlit --timeout=180s
```

The `startupProbe` allows 150s of cold start, so a slow first model load is not a
CrashLoop. If rollout stalls: `kubectl -n ai-apps describe pod -l app.kubernetes.io/name=langgraph-streamlit`.

## Phase 3 — verify the hardening actually applied

This is the phase worth demoing. It turns claims into observations.

```powershell
# Runs as uid 10001, not root
kubectl -n ai-apps exec deploy/langgraph-streamlit -- id
# expect: uid=10001 gid=10001

# Root filesystem really is read-only
kubectl -n ai-apps exec deploy/langgraph-streamlit -- sh -c "touch /probe 2>&1 || echo 'READ-ONLY OK'"
# expect: READ-ONLY OK

# ...but the scratch mounts are writable, which is why the app still works
kubectl -n ai-apps exec deploy/langgraph-streamlit -- sh -c "touch /tmp/ok && echo 'TMP WRITABLE OK'"

# No service account token mounted
kubectl -n ai-apps exec deploy/langgraph-streamlit -- sh -c "ls /var/run/secrets/kubernetes.io 2>&1 || echo 'NO SA TOKEN OK'"

# Egress policy in force
kubectl -n ai-apps get networkpolicy
```

> k3d ships Flannel, which does **not** enforce NetworkPolicy. Say this out loud in
> the demo rather than letting an interviewer catch it: the manifests are correct and
> enforce on any CNI that implements the API (Calico/Cilium). To enforce locally,
> recreate the cluster with `k3d cluster create ai-demo --k3s-arg "--disable-network-policy@server:*"`
> and install Calico. Knowing where your local environment diverges from production
> is the point, not a gap.

## Phase 4 — reach the UI

```powershell
kubectl -n ai-apps port-forward svc/langgraph-streamlit 8501:8501
```

Then http://localhost:8501 — or http://streamlit.localhost:8089 via the k3d ingress.
Rancher → Workloads → `ai-apps` shows logs, scaling and metrics for the walkthrough.

## Phase 5 — the actual demo, in order

1. **Rancher UI**: the pod running, non-root, probes green. 30 seconds.
2. **Phase 3 commands**: live-run two of them. This is the differentiator — most
   candidates show an app, not a hardened deployment.
3. **`python -m evals.runner --tasks bug-002`**: one task end to end, agent loop
   visible, hidden tests applied after, deterministic pass/fail.
4. **The numbers**: Pass@1 vs recovery rate, and why they're reported separately.

Total: under 10 minutes. Do not narrate the code — narrate the decisions.

## Rollback

```powershell
kubectl delete -k k8s/
```
