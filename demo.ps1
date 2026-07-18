# demo.ps1 — one-command interview demo launcher for langgraph_ollama + md-mcp.
#
#   .\demo.ps1              # pre-flight checks, start everything, open browser
#   .\demo.ps1 -Demo        # same, but apply the .env.demo preset first
#   .\demo.ps1 -NoBrowser   # don't open browser tabs
#   .\demo.ps1 -ChecksOnly  # run pre-flight checks and exit
#
# Starts: LGTM observability stack (Grafana/Loki/Tempo/Prometheus/collector),
# the Streamlit app, and verifies Ollama + models + the md-mcp Docker image.

param(
    [switch]$Demo,
    [switch]$NoBrowser,
    [switch]$ChecksOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

$script:Failures = @()

function Step($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Fail($msg, $fix) {
    Write-Host "  [XX] $msg" -ForegroundColor Red
    if ($fix) { Write-Host "       Fix: $fix" -ForegroundColor Red }
    $script:Failures += $msg
}

function Read-DotEnv($path) {
    $vars = @{}
    if (Test-Path $path) {
        foreach ($line in Get-Content $path) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$' -and $line -notmatch '^\s*#') {
                $vars[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
            }
        }
    }
    return $vars
}

# ---------------------------------------------------------------------------
# 0. Env preset
# ---------------------------------------------------------------------------
if ($Demo) {
    Step "Applying .env.demo preset"
    if (-not (Test-Path "$RepoRoot\.env.demo")) {
        Fail ".env.demo not found" "create it or run without -Demo"
    } else {
        if (Test-Path "$RepoRoot\.env") {
            Copy-Item "$RepoRoot\.env" "$RepoRoot\.env.backup" -Force
            Ok "existing .env backed up to .env.backup"
        }
        # Carry a real Tavily key over from the existing .env if present.
        $existing = Read-DotEnv "$RepoRoot\.env"
        Copy-Item "$RepoRoot\.env.demo" "$RepoRoot\.env" -Force
        if ($existing["TAVILY_API_KEY"] -and $existing["TAVILY_API_KEY"] -ne "your_tavily_api_key_here") {
            (Get-Content "$RepoRoot\.env") -replace '^TAVILY_API_KEY=.*', "TAVILY_API_KEY=$($existing['TAVILY_API_KEY'])" |
                Set-Content "$RepoRoot\.env"
            Ok "kept TAVILY_API_KEY from previous .env"
        }
        Ok ".env.demo -> .env"
    }
}

$envVars = Read-DotEnv "$RepoRoot\.env"
$model      = $envVars["OLLAMA_MODEL"]
$ollamaUrl  = if ($envVars["OLLAMA_BASE_URL"]) { $envVars["OLLAMA_BASE_URL"] } else { "http://localhost:11434" }
$mdFolder   = $envVars["MD_MCP_FOLDER"]
$mdUrl      = $envVars["MD_MCP_URL"]
$embedModel = if ($envVars["OLLAMA_EMBED_MODEL"]) { $envVars["OLLAMA_EMBED_MODEL"] } else { "nomic-embed-text" }

# ---------------------------------------------------------------------------
# 1. Pre-flight checks
# ---------------------------------------------------------------------------
Step "Pre-flight: .env"
if (-not $model) { Fail "OLLAMA_MODEL not set in .env" "copy .env.example to .env and set OLLAMA_MODEL" }
else             { Ok "OLLAMA_MODEL=$model" }
if ($mdFolder) {
    if (Test-Path $mdFolder) { Ok "MD_MCP_FOLDER=$mdFolder" }
    else { Fail "MD_MCP_FOLDER points to a missing folder: $mdFolder" "fix the path in .env" }
} else {
    Warn "MD_MCP_FOLDER not set - RAG chatbot runs without md-mcp notes tools"
}

Step "Pre-flight: Docker engine"
docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Warn "Docker engine not responding - starting Docker Desktop..."
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    # Cold starts of Docker Desktop on this machine can take 5+ minutes.
    $deadline = (Get-Date).AddMinutes(6)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        docker info 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
    }
}
docker info 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { Ok "Docker engine up" }
else { Fail "Docker engine did not come up" "start Docker Desktop manually, then re-run" }

Step "Pre-flight: Ollama + models"
try {
    $tags = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -TimeoutSec 5
    Ok "Ollama reachable at $ollamaUrl"
    $names = @($tags.models | ForEach-Object { $_.name })
    foreach ($m in @($model, $embedModel)) {
        if (-not $m) { continue }
        # Ollama lists "name:tag"; accept exact or name-only matches.
        if ($names -contains $m -or $names -contains "$($m):latest" -or ($names | Where-Object { $_ -like "$m*" })) {
            Ok "model present: $m"
        } else {
            Fail "model missing: $m" "run: ollama pull $m"
        }
    }
    # Presence is not enough: cloud-routed tags can be retired server-side and
    # still appear installed (glm-5:cloud died this way with 410 Gone). Prove
    # the chat model actually generates before going on stage.
    if ($model) {
        try {
            $body = @{ model = $model; stream = $false
                       messages = @(@{ role = "user"; content = "say ok" })
                       options = @{ num_predict = 5 } } | ConvertTo-Json -Depth 5
            $resp = Invoke-RestMethod -Uri "$ollamaUrl/api/chat" -Method Post -Body $body -TimeoutSec 90
            if ($resp.message) { Ok "live generation test passed: $model" }
            else { Fail "chat model returned no message: $model" "try another model in .env" }
        } catch {
            Fail "chat model failed a live generation test: $model ($($_.Exception.Message))" "model may be retired/broken - pick another in .env (e.g. glm-5.2:cloud)"
        }
    }
} catch {
    Fail "Ollama not reachable at $ollamaUrl" "start Ollama, then re-run"
}

Step "Pre-flight: md-mcp Docker image"
if ($mdFolder) {
    docker image inspect ly2xxx/md-mcp:latest 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "ly2xxx/md-mcp:latest present" }
    else {
        Warn "pulling ly2xxx/md-mcp:latest..."
        docker pull ly2xxx/md-mcp:latest
        if ($LASTEXITCODE -eq 0) { Ok "image pulled" } else { Fail "could not pull ly2xxx/md-mcp:latest" "check network / Docker Hub" }
    }
} else {
    Ok "skipped (MD_MCP_FOLDER not set)"
}

if ($script:Failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Pre-flight FAILED ($($script:Failures.Count) issue(s)) - fix the items above and re-run." -ForegroundColor Red
    exit 1
}
if ($ChecksOnly) {
    Write-Host ""
    Write-Host "Pre-flight PASSED - all checks green." -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------------------
# 2. Observability stack
# ---------------------------------------------------------------------------
Step "Starting observability stack (Grafana/Loki/Tempo/Prometheus/collector)"
docker compose -f docker-compose.observability.yml up -d
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" "see output above"; exit 1 }

$deadline = (Get-Date).AddMinutes(2)
$grafanaOk = $false; $lokiOk = $false
while ((Get-Date) -lt $deadline -and -not ($grafanaOk -and $lokiOk)) {
    if (-not $grafanaOk) {
        try { $h = Invoke-RestMethod -Uri "http://localhost:3001/api/health" -TimeoutSec 3
              if ($h.database -eq "ok") { $grafanaOk = $true; Ok "Grafana healthy (http://localhost:3001)" } } catch {}
    }
    if (-not $lokiOk) {
        try { $r = Invoke-WebRequest -Uri "http://localhost:3100/ready" -TimeoutSec 3
              if ($r.Content -match "ready") { $lokiOk = $true; Ok "Loki ready" } } catch {}
    }
    if (-not ($grafanaOk -and $lokiOk)) { Start-Sleep -Seconds 4 }
}
if (-not $grafanaOk) { Warn "Grafana not healthy yet - it may need a few more seconds" }
if (-not $lokiOk)    { Warn "Loki not ready yet - logs may lag for a minute" }

# ---------------------------------------------------------------------------
# 2b. md-mcp server (long-lived HTTP container)
# ---------------------------------------------------------------------------
# When MD_MCP_URL points at localhost:8000, run one persistent md-mcp container
# serving MD_MCP_FOLDER over streamable-http, exporting OTel to the collector.
# This is what makes the single distributed trace span both services — and it
# avoids the ~10s `docker run` cost the stdio fallback pays on every session.
if ($mdUrl -and $mdUrl -match "localhost:8000" -and $mdFolder) {
    Step "Starting md-mcp HTTP server container"
    $existing = docker ps -q --filter "name=md-mcp-demo"
    if ($existing) {
        Ok "md-mcp-demo container already running"
    } else {
        docker rm -f md-mcp-demo 2>$null | Out-Null
        docker run -d --name md-mcp-demo `
            -p 8000:8000 `
            -e MD_TRANSPORT=http `
            -e OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4317 `
            -e OTEL_SERVICE_NAME=md-mcp `
            -v "${mdFolder}:/data:ro" `
            ly2xxx/md-mcp:latest | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "md-mcp container failed to start" "check: docker logs md-mcp-demo" }
    }
    $deadline = (Get-Date).AddSeconds(45); $mcpOk = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-NetConnection -ComputerName localhost -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue) { $mcpOk = $true; break }
        Start-Sleep -Seconds 3
    }
    if ($mcpOk) { Ok "md-mcp serving MCP at $mdUrl" }
    else { Warn "md-mcp port 8000 not answering yet - app will fall back gracefully" }
}

# ---------------------------------------------------------------------------
# 3. Streamlit app
# ---------------------------------------------------------------------------
Step "Starting Streamlit app"
$portBusy = Test-NetConnection -ComputerName localhost -Port 8501 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($portBusy) {
    Ok "port 8501 already serving - reusing running app"
} else {
    Start-Process -WorkingDirectory $RepoRoot -WindowStyle Minimized uv -ArgumentList "run","streamlit","run","app.py","--server.headless","true"
    $deadline = (Get-Date).AddMinutes(2)
    $appOk = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-NetConnection -ComputerName localhost -Port 8501 -InformationLevel Quiet -WarningAction SilentlyContinue) { $appOk = $true; break }
        Start-Sleep -Seconds 3
    }
    if ($appOk) { Ok "app serving on http://localhost:8501" }
    else { Fail "app did not start within 2 minutes" "run manually: uv run streamlit run app.py"; exit 1 }
}

# ---------------------------------------------------------------------------
# 4. Open browser + summary
# ---------------------------------------------------------------------------
$dashboardUrl = "http://localhost:3001/d/cfr1bvchmx4owb/?from=now-15m&to=now&refresh=5s"
if (-not $NoBrowser) {
    Step "Opening browser tabs"
    Start-Process "http://localhost:8501"
    Start-Process $dashboardUrl
}

Write-Host ""
Write-Host "=============================================================" -ForegroundColor Green
Write-Host " Demo ready." -ForegroundColor Green
Write-Host "   App        http://localhost:8501"
Write-Host "   Grafana    $dashboardUrl  (admin/admin)"
Write-Host "   Prometheus http://localhost:9090"
Write-Host "   Tempo API  http://localhost:3200   Loki API http://localhost:3100"
Write-Host ""
Write-Host " First page load compiles the agent graph - give it a moment."
Write-Host " Run a RAG query, then watch the dashboard light up (~10s lag)."
Write-Host "=============================================================" -ForegroundColor Green
