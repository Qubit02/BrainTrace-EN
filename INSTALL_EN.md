# BrainTrace Execution Guide

> **BrainTrace** is a knowledge-graph–based AI chatbot system that automatically builds a knowledge graph from uploaded documents and generates accurate answers.

## Table of Contents

- [System Requirements](#system-requirements)
- [Detailed Installation Guide](#detailed-installation-guide)
- [Access Information](#access-information)
- [Additional Resources](#additional-resources)

## System Requirements

### Basic Requirements

- **Operating System**: Windows 10/11
- **Python**: 3.12
- **Node.js**: 20.19.0 or higher
- **Neo4j**: see below
- **Ollama**: see below

### Hardware Requirements

#### Profile A: Use External LLM / Do Not Use Local LLM

| Profile                                      | CPU     | RAM                             | Disk                    |
| -------------------------------------------- | ------- | -------------------------------- | ----------------------- |
| **A) External LLM / No Local LLM**           | 2–4 cores | **≥ 8GB**                        | 10–20GB                 |
| **B) Local LLM (Ollama 7B, Q4)**             | 4–8 cores | **Minimum 12GB (16GB recommended)** | 30–50GB+ (models/cache) |

**Recommended Specs**

- CPU: 6 cores  
- Memory: 16GB RAM  
- Storage: 50GB+ free space (for AI models and databases)

## Detailed Installation Guide (Choose one: Native run or [Run with Docker](#run-with-docker)) <a id="detailed-installation-guide"></a>

### 1. Native Run

```bash
git clone https://github.com/Qubit02/BrainTrace.git
cd BrainTrace
```

### 1.1 Backend Setup

#### 1.1.1 Create and Activate Python Virtual Environment (start from BrainTrace/)

```bash
cd backend

# Create venv
python -m venv venv
```

#### Activate Virtual Environment

```
# Windows
venv\Scriptsctivate
```

```
# macOS/Linux
source venv/bin/activate
```

#### 1.1.2 Install Dependencies

```bash
pip install -r requirements.txt
```

#### 1.1.3 Set Environment Variables

```bash
# Create .env -> backend/.env

# Add model install location when using Ollama
OLLAMA_MODELS=./models/ollama

# API key
# OPENAI_API_KEY=your_api_key_here
```

### 1.2 Database Setup

#### 1.2.1 Install Neo4j

> The scripts below automatically detect the execution location. In your terminal, paste one of the following snippets **at the repository root (BrainTrace/)** or inside **backend/**.

#### Windows Installation (copy the snippet that matches your terminal: PowerShell or Git Bash)

<details>
<summary><strong>PowerShell (Windows)</strong></summary>
  
```powershell
param(
  [string]$Version = 'latest'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --- 0) Settings & Path Rules -----------------------------------------------
$CWD = (Get-Location).Path
$HereIsBackend = ((Split-Path -Leaf $CWD) -eq 'backend')
$HereHasBackendChild = Test-Path (Join-Path $CWD 'backend')

if ($HereIsBackend) {
  $ROOT    = Split-Path $CWD -Parent
  $BACKEND = $CWD
  $TARGET  = Join-Path $CWD 'neo4j'
}
elseif ($HereHasBackendChild) {
  $ROOT    = $CWD
  $BACKEND = Join-Path $ROOT 'backend'
  $TARGET  = Join-Path $BACKEND 'neo4j'
}
else {
  throw "Do not run here. Run at the repo root (where the backend folder is visible) or inside the backend folder."
}

$STAGE  = Join-Path $ROOT 'neo4j_stage'

if (-not ([Net.ServicePointManager]::SecurityProtocol -band [Net.SecurityProtocolType]::Tls12)) {
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

# --- 1) Auto-detect latest version ------------------------------------------
function Get-LatestNeo4jVersion {
  $pages = @(
    'https://neo4j.com/graph-data-science-software/',
    'https://neo4j.com/deployment-center/'
  )

  foreach ($u in $pages) {
    try {
      $resp = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 30
    } catch { continue }

    $links = @()
    if ($resp.Links) { $links = $resp.Links }

    $href = $links |
      Where-Object { $_.href -match 'download-thanks\.html' } |
      Where-Object { $_.href -match 'edition=community' } |
      Where-Object { ($_.href -match 'winzip') -or ($_.href -match 'packaging=zip') } |
      Where-Object { $_.href -match 'release=' } |
      Select-Object -First 1 -ExpandProperty href

    if ($href) {
      $q = ([uri]"https://dummy.local/?$([uri]$href).Query").Query.TrimStart('?')
      $pairs = @{}
      foreach ($kv in $q -split '&') {
        $k,$v = $kv -split '=',2
        if ($k) { $pairs[$k] = [uri]::UnescapeDataString($v) }
      }
      if ($pairs['release']) { return $pairs['release'] }
    }

    $m = [regex]::Match($resp.Content, 'Neo4j Community Edition\s+(?<v>(2025\.\d{2}\.\d+|\d+\.\d+\.\d+))')
    if ($m.Success) { return $m.Groups['v'].Value }
  }

  throw "Failed to find the latest version. Specify something like -Version '5.26.12'."
}

if ($Version -eq 'latest') { $Version = Get-LatestNeo4jVersion }
Write-Host "Using Neo4j Community version: $Version"

# --- 2) Download -------------------------------------------------------------
$zipFileName = "neo4j-community-$Version-windows.zip"
$ZIPPATH     = Join-Path $STAGE $zipFileName

$urls = @(
  "https://dist.neo4j.org/$zipFileName",
  "https://neo4j.com/artifact.php?name=$zipFileName"
)

if (Test-Path $STAGE) { Remove-Item $STAGE -Recurse -Force }
New-Item -ItemType Directory -Path $STAGE | Out-Null
if (-not (Test-Path $BACKEND)) { New-Item -ItemType Directory -Path $BACKEND | Out-Null }

function Try-Download($url) {
  try {
    Write-Host "Downloading via HttpClient: $url"
    if (-not ([System.Management.Automation.PSTypeName]'System.Net.Http.HttpClient').Type) {
      Add-Type -AssemblyName 'System.Net.Http'
    }
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromMinutes(15)
    $resp = $client.GetAsync($url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
    $resp.EnsureSuccessStatusCode()
    $fs = [System.IO.FileStream]::new($ZIPPATH, [System.IO.FileMode]::Create)
    $resp.Content.CopyToAsync($fs).Wait()
    $fs.Close(); $client.Dispose()
    if ((Get-Item $ZIPPATH).Length -gt 10MB) { return $true }
    else { Remove-Item $ZIPPATH -Force }
  } catch {
    Write-Host "Download failed: $($_.Exception.Message)"
    return $false
  }
}

$ok = $false
foreach ($u in $urls) { if (Try-Download $u) { $ok = $true; break } }
if (-not $ok) { throw "Neo4j ZIP download failed" }

# --- 3) Unzip & prepare folder ----------------------------------------------
Expand-Archive -Path $ZIPPATH -DestinationPath $STAGE -Force

$extracted = Get-ChildItem -Path $STAGE -Directory |
  Where-Object { $_.Name -like "neo4j-community-*" } |
  Select-Object -First 1
if (-not $extracted) { throw "Cannot find the extracted folder." }

$prepared = Join-Path $STAGE "neo4j"
if (Test-Path $prepared) { Remove-Item $prepared -Recurse -Force }
Rename-Item -Path $extracted.FullName -NewName "neo4j"

# --- 4) Move to target (fixed folder name) -----------------------------------
$TARGET_PARENT = Split-Path $TARGET -Parent
if (-not (Test-Path $TARGET_PARENT)) {
  New-Item -ItemType Directory -Path $TARGET_PARENT | Out-Null
}
if (Test-Path $TARGET) { Remove-Item $TARGET -Recurse -Force }

Move-Item -LiteralPath $prepared -Destination $TARGET_PARENT -Force
$justMoved = Join-Path $TARGET_PARENT 'neo4j'
if ((Split-Path $TARGET -Leaf) -ne 'neo4j') {
  if (Test-Path $justMoved) {
    Rename-Item -Path $justMoved -NewName (Split-Path $TARGET -Leaf) -ErrorAction SilentlyContinue
  }
}

# --- 5) Edit conf (based on final path) --------------------------------------
$CONF = Join-Path $TARGET 'conf
eo4j.conf'
if (-not (Test-Path $CONF)) { throw "neo4j.conf not found: $CONF" }

$text = Get-Content -LiteralPath $CONF -Raw
$text = $text -replace "`r?`n", "`r`n"

$pattern = '^[	 ]*#?[	 ]*dbms\.security\.auth_enabled[	 ]*=[	 ]*(true|false)([	 ]*#.*)?$'
if ($text -match $pattern) {
  $text = [Regex]::Replace($text, $pattern, 'dbms.security.auth_enabled=false',
    [System.Text.RegularExpressions.RegexOptions]::Multiline)
} else {
  if ($text.Length -gt 0 -and $text[-1] -ne "`n") { $text += "`r`n" }
  $text += 'dbms.security.auth_enabled=false' + "`r`n"
}

$bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($text)
[System.IO.File]::WriteAllBytes($CONF, $bytes)

# --- 6) Clean stage & finish -------------------------------------------------
Remove-Item $STAGE -Recurse -Force

Write-Host "✅ Neo4j $Version is ready"
```
</details> 

<details> <summary><strong>Git Bash (Windows)</strong></summary>

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-latest}"

# ── 0) Path rules ─────────────────────────────────────────────
CWD="$(pwd)"
if [[ "$(basename "$CWD")" == "backend" ]]; then
  ROOT="$(dirname "$CWD")"
  BACKEND="$CWD"
  TARGET="$CWD/neo4j"
elif [[ -d "$CWD/backend" ]]; then
  ROOT="$CWD"
  BACKEND="$ROOT/backend"
  TARGET="$BACKEND/neo4j"
else
  echo "❌ Run at the repo root (where the backend folder is visible) or inside backend." >&2
  exit 1
fi
STAGE="$ROOT/neo4j_stage"

mkdir -p "$STAGE" "$BACKEND"

# ── 1) Auto-detect latest version ─────────────────────────────
if [[ "$VERSION" == "latest" ]]; then
  echo "🔍 Fetching latest Neo4j Community version..."
  VERSION="$(curl -fsSL https://dist.neo4j.org/ |              grep -Eo 'neo4j-community-[0-9.]+-windows.zip' |              sort -V | tail -1 | grep -Eo '[0-9.]+')" || true
  [[ -z "$VERSION" ]] && VERSION="5.26.12"
fi
echo "Using Neo4j Community version: $VERSION"

# ── 2) Download ───────────────────────────────────────────────
ZIPFILE="neo4j-community-${VERSION}-windows.zip"
URLS=(
  "https://dist.neo4j.org/${ZIPFILE}"
  "https://neo4j.com/artifact.php?name=${ZIPFILE}"
)

cd "$STAGE"
for URL in "${URLS[@]}"; do
  echo "⬇️  Downloading: $URL"
  if curl -fL --connect-timeout 20 -o "$ZIPFILE" "$URL"; then
    [[ -s "$ZIPFILE" ]] && break
  fi
done

[[ ! -s "$ZIPFILE" ]] && { echo "❌ Download failed"; exit 1; }

# ── 3) Unzip & tidy ───────────────────────────────────────────
unzip -q -o "$ZIPFILE"
EXTRACTED="$(find . -maxdepth 1 -type d -name "neo4j-community-*")"
[[ -z "$EXTRACTED" ]] && { echo "❌ Unzip failed"; exit 1; }
rm -rf neo4j && mv "$EXTRACTED" neo4j

# ── 4) Move to target ────────────────────────────────────────
rm -rf "$TARGET"
mkdir -p "$(dirname "$TARGET")"
mv neo4j "$TARGET"

# ── 5) Edit conf (v4/v5 compatible) ──────────────────────────
CONF="$TARGET/conf/neo4j.conf"
[[ ! -f "$CONF" ]] && { echo "❌ conf not found: $CONF"; exit 1; }

# Normalize lines and handle keys
TMP="$(mktemp)"
awk '
BEGIN{found4=0;found5=0}
{
  if($0 ~ /^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=/){
    print "dbms.security.auth_enabled=false"; found4=1; next
  }
  if($0 ~ /^[[:space:]]*#?[[:space:]]*dbms\.security\.authentication_enabled[[:space:]]*=/){
    print "dbms.security.authentication_enabled=false"; found5=1; next
  }
  print $0
}
END{
  if(!found4) print "dbms.security.auth_enabled=false";
  if(!found5) print "dbms.security.authentication_enabled=false";
}' "$CONF" > "$TMP"
mv "$TMP" "$CONF"

# ── 6) Cleanup & output ──────────────────────────────────────
rm -rf "$STAGE"
echo "✅ Neo4j $VERSION installed"
```
</details>


#### macOS / Linux Installation

<details><summary><strong>macOS / Linux</strong></summary>

```bash
( set -eu
  set +u; set -o pipefail 2>/dev/null || true; set -u

  : "${VERSION:=latest}"

  CWD="$PWD"
  if [[ "$(basename "$CWD")" == "backend" ]]; then
    ROOT="$(dirname "$CWD")"; BACKEND="$CWD"; TARGET="$BACKEND/neo4j"
  elif [[ -d "$CWD/backend" ]]; then
    ROOT="$CWD"; BACKEND="$ROOT/backend"; TARGET="$BACKEND/neo4j"
  else {
    echo "❌ Do not run here. Run at the repo root (where the backend folder is visible) or inside backend/." >&2
    exit 1
  fi
  STAGE="$ROOT/neo4j_stage"

  get_latest_version() {
    local pages=(
      "https://neo4j.com/graph-data-science-software/"
      "https://neo4j.com/deployment-center/"
    )
    local html rel
    for u in "${pages[@]}"; do
      html="$(curl -fsSL --max-time 30 "$u" || true)" || true
      [[ -z "$html" ]] && continue
      rel="$(printf '%s' "$html"         | grep -Eo 'https?://[^"]*download-thanks[^"]+'         | grep -E 'edition=community'         | grep -E 'unix|packaging=tar(\.gz)?|packaging=zip'         | grep -Eo 'release=[0-9]+\.[0-9]+\.[0-9]+'         | head -n1 | cut -d= -f2)"
      [[ -n "$rel" ]] && { printf '%s' "$rel"; return 0; }
      rel="$(printf '%s' "$html"         | grep -Eo 'Neo4j Community Edition[[:space:]]+[0-9]+\.[0-9]+\.[0-9]+'         | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+'         | head -n1)"
      [[ -n "$rel" ]] && { printf '%s' "$rel"; return 0; }
    done
    return 1
  }

  if [[ "$VERSION" == "latest" ]]; then
    echo "🌐 Checking latest version..."
    if ! VERSION="$(get_latest_version)"; then
      echo "❌ Failed to detect the latest version. Set VERSION env var (e.g., export VERSION=5.26.12)" >&2
      exit 1
    fi
  fi
  echo "✅ Using Neo4j Community version: $VERSION"

  TAR="neo4j-community-$VERSION-unix.tar.gz"
  URLS=(
    "https://dist.neo4j.org/$TAR"
    "https://neo4j.com/artifact.php?name=$TAR"
  )

  rm -rf "$STAGE"; mkdir -p "$STAGE" "$BACKEND"
  ARCHIVE="$STAGE/$TAR"

  download() {
    local url="$1"
    echo "⬇️  Downloading: $url"
    curl -fL --retry 5 --retry-delay 2       --connect-timeout 25 --max-time 1800       --speed-time 30 --speed-limit 10240       -o "$ARCHIVE" "$url"
  }
  ok=0
  for u in "${URLS[@]}"; do
    if download "$u"; then
      sz="$(wc -c <"$ARCHIVE" 2>/dev/null || echo 0)"
      if [[ "$sz" -gt $((10*1024*1024)) ]]; then ok=1; break; else rm -f "$ARCHIVE"; fi
    fi
  done
  [[ $ok -eq 1 ]] || { echo "❌ Neo4j tarball download failed" >&2; exit 1; }

  tar -xzf "$ARCHIVE" -C "$STAGE"
  extracted="$(find "$STAGE" -maxdepth 1 -type d -name 'neo4j-community-*' | head -n1)"
  [[ -n "$extracted" ]] || { echo "❌ Cannot find extracted folder." >&2; exit 1; }

  prepared="$STAGE/neo4j"
  rm -rf "$prepared"; mv "$extracted" "$prepared"

  CONF="$prepared/conf/neo4j.conf"
  [[ -f "$CONF" ]] || { echo "❌ neo4j.conf not found: $CONF" >&2; exit 1; }

  if command -v gsed >/dev/null 2>&1; then SED="gsed"; else SED="sed"; fi
  if "$SED" --version >/dev/null 2>/dev/null; then
    if "$SED" -E -n 's/^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=.*/X/p' "$CONF" | grep -q .; then
      "$SED" -i -E 's/^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=[[:space:]]*(true|false)[[:space:]]*$/dbms.security.auth_enabled=false/' "$CONF"
    else
      printf '\n%s\n' 'dbms.security.auth_enabled=false' >> "$CONF"
    fi
  else
    if "$SED" -E -n 's/^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=[[:space:]]*(true|false)[[:space:]]*$/X/p' "$CONF" | grep -q .; then
      "$SED" -i '' -E 's/^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=[[:space:]]*(true|false)[[:space:]]*$/dbms.security.auth_enabled=false/' "$CONF"
    else
      printf '\n%s\n' 'dbms.security.auth_enabled=false' >> "$CONF"
    fi
  fi

  mkdir -p "$(dirname "$TARGET")"
  rm -rf "$TARGET"
  mv "$prepared" "$(dirname "$TARGET")"
  if [[ "$(basename "$TARGET")" != "neo4j" && -d "$(dirname "$TARGET")/neo4j" ]]; then
    mv "$(dirname "$TARGET")/neo4j" "$TARGET"
  fi

  rm -rf "$STAGE"
  echo ""
  echo "✅ Neo4j $VERSION is ready"
  echo "📂 Path: $TARGET"
  echo "🛠️ conf updated: $CONF"
  echo "🚀 Example:  $TARGET/bin/neo4j console"
)
```
</details>

#### 1.2.2 Ollama Setup (Local AI Model)

[Download Ollama](https://ollama.com/download)

#### 1.2.3 Run Backend

```bash
cd frontend
npm install
```

### 1.3 Run Frontend

#### 1.3.1 Install Dependencies (start from BrainTrace/)

```bash
cd frontend
npm install
```

#### 1.3.2 Start Frontend

```bash
npm run dev
```
---
### 2. Run with Docker<a id="run-with-docker"></a>

```bash
# Clone repo
git clone https://github.com/Qubit02/BrainTrace.git
cd BrainTrace

# Run with Docker Compose
docker-compose up -d

# Open in browser
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000
# Neo4j: http://localhost:7474
```

### Run Entire Stack

```bash
# Start all services
docker-compose up -d
```

### Run Services Individually

```bash
# Backend only
docker-compose up backend

# Frontend only
docker-compose up frontend

# Official neo4j/ollama containers
docker-compose up neo4j ollama
```

### Stop & Clean Up

```bash
# Stop services
docker-compose down

# Remove volumes
docker-compose down -v

# Rebuild images
docker-compose build --no-cache
```

## Access Information

| Service           | URL                        | Description                 |
| ----------------- | -------------------------- | --------------------------- |
| **Frontend**      | http://localhost:5173      | Main web application        |
| **Backend API**   | http://localhost:8000      | REST API server             |
| **Swagger Docs**  | http://localhost:8000/docs | API documentation & testing |
| **Neo4j Browser** | http://localhost:7474      | Graph database management   |
| **Ollama API**    | http://localhost:11434     | Local AI model API          |

## Additional Resources

- [Project README](./README.md)
- [Knowledge Graph Docs](./KNOWLEDGE_GRAPH.md)
- [API Docs](http://localhost:8000/docs)
- [Neo4j Docs](https://neo4j.com/docs/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)

## Contributing

If you’d like to contribute:

1. Open an issue to report bugs or request features  
2. Fork the repo and submit a Pull Request  
3. Join code reviews and testing

## Support

If you encounter issues or need help:

- Create a [GitHub Issue](https://github.com/OSSBrainTrace/BrainTrace/issues)  
- Check project documentation  
- Use community forums

---

**Note**: Downloading AI models can require significant disk space. You may need up to 10GB of free space per model file.
