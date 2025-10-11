# BrainTrace Run Guide

> **BrainTrace** is a knowledge-graph–based AI chatbot system. Upload documents, and it automatically builds a knowledge graph and generates accurate answers.

## Table of Contents

- [System Requirements](#system-requirements)
- [Detailed Setup Guide](#detailed-setup-guide)
- [Access Information](#access-information)
- [Additional Resources](#additional-resources)

## System Requirements

### Basic Requirements

- **Operating System**: Windows 10/11
- **Python**: 3.12
- **Node.js**: 20.19.0 or later
- **Neo4j**: See below
- **Ollama**: See below

### Hardware Requirements

#### Profile A: Use External LLM / Do Not Use Local LLM

| Profile                                       | CPU     | RAM                              | Disk                    |
| --------------------------------------------- | ------- | -------------------------------- | ----------------------- |
| **A) Use external LLM / no local LLM**        | 2–4 cores | **≥ 8GB**                       | 10–20GB (images/logs)   |
| **B) Local LLM (Ollama 7B, Q4 baseline) use** | 4–8 cores | **Min 12GB (16GB recommended)** | 30–50GB+ (models/cache) |

**Recommended Specs**

- CPU: 6 cores
- Memory: 16GB RAM
- Storage: 50GB+ free space (for AI models and database)


## Detailed Setup Guide

### 1. Run with Docker

```bash
# Clone the repository
git clone https://github.com/OSSBrainTrace/BrainTrace.git
cd BrainTrace

# Run with docker-compose
docker-compose up -d

# Open in your browser
# Frontend:  http://localhost:5173
# Backend API: http://localhost:8000
# Neo4j:     http://localhost:7474
```

### Run the full stack

```bash
# Start all services
docker-compose up -d

# Follow logs
docker-compose logs -f

# Start specific services only
docker-compose up backend frontend
```

### Run services individually

```bash
# Backend only
docker-compose up backend

# Frontend only
docker-compose up frontend

# Database only
docker-compose up neo4j ollama
```

### Stop & clean up services

```bash
# Stop services
docker-compose down

# Remove volumes as well
docker-compose down -v

# Rebuild images
docker-compose build --no-cache
```


### 2. Run in a regular environment

```bash
git clone https://github.com/Qubit02/BrainTrace.git
cd BrainTrace
```

### 2.1 Backend Setup

#### 2.1.1 Create and activate a Python virtual environment

```bash
cd backend

# Create venv
python -m venv venv
```

#### Activate the virtual environment

```
# Windows
venv\Scripts\activate
```

```
# macOS/Linux
source venv/bin/activate
```

#### 2.1.2 Install dependencies

```bash
pip install -r requirements.txt
```

#### 2.1.3 Set environment variables

```bash
# Create .env at -> backend/.env

# API keys and inputs
# OPENAI_API_KEY=your_api_key_here
```

### 2.2 Database Setup

### 2.2.1 Install Neo4j

> The scripts below auto-detect the working directory. Run them from **the repository root (where the backend/ folder is visible)** or from **backend/**.

<details>
<summary><strong>PowerShell (Windows)</strong></summary>

```powershell
# Neo4j Community automatic installer (Windows PowerShell 5.1+ / PowerShell 7+)
# - Run from repository root (where backend/ is visible) or from backend/
# - Auto-detects latest version / fast HttpClient download / safe conf edit

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --- 0) Config & path rules ---------------------------------------------------
if (-not $Version) { $Version = 'latest' }   # Override with: -Version '5.26.12' if needed

$CWD = (Get-Location).Path
$HereIsBackend = ((Split-Path -Leaf $CWD) -eq 'backend')
$HereHasBackendChild = Test-Path (Join-Path $CWD 'backend')

if ($HereIsBackend) {
  # Running under backend/ → ./neo4j
  $ROOT    = Split-Path $CWD -Parent
  $BACKEND = $CWD
  $TARGET  = Join-Path $CWD 'neo4j'
}
elseif ($HereHasBackendChild) {
  # Running at repo root → backend/neo4j
  $ROOT    = $CWD
  $BACKEND = Join-Path $ROOT 'backend'
  $TARGET  = Join-Path $BACKEND 'neo4j'
}
else {
  throw "Do not run here. Run from the repo root (where backend is visible) or from backend."
}

$STAGE  = Join-Path $ROOT 'neo4j_stage'

# Enforce TLS 1.2 (legacy environments)
if (-not ([Net.ServicePointManager]::SecurityProtocol -band [Net.SecurityProtocolType]::Tls12)) {
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

# --- 1) Auto-detect latest version -------------------------------------------
function Get-LatestNeo4jVersion {
  $pages = @(
    'https://neo4j.com/graph-data-science-software/',
    'https://neo4j.com/deployment-center/'
  )

  foreach ($u in $pages) {
    try { $resp = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 30 } catch { continue }

    $links = @()
    if ($resp.Links) { $links = $resp.Links }

    $href = $links `
      | Where-Object { $_.href -match 'download-thanks\.html' } `
      | Where-Object { $_.href -match 'edition=community' } `
      | Where-Object { ($_.href -match 'winzip') -or ($_.href -match 'packaging=zip') } `
      | Where-Object { $_.href -match 'release=' } `
      | Select-Object -First 1 -ExpandProperty href

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

  throw "Failed to find the latest version. Specify one like -Version '5.26.12'."
}

if ($Version -eq 'latest') { $Version = Get-LatestNeo4jVersion }
Write-Host "Using Neo4j Community version: $Version"

# --- 2) Download --------------------------------------------------------------
$zipFileName = "neo4j-community-$Version-windows.zip"
$ZIPPATH     = Join-Path $STAGE $zipFileName

$urls = @(
  "https://dist.neo4j.org/$zipFileName",                   # CDN (fast)
  "https://neo4j.com/artifact.php?name=$zipFileName"       # Fallback
)

# Init stage
if (Test-Path $STAGE) { Remove-Item $STAGE -Recurse -Force }
New-Item -ItemType Directory -Path $STAGE | Out-Null
if (-not (Test-Path $BACKEND)) { New-Item -ItemType Directory -Path $BACKEND | Out-Null }

function Try-Download($url) {
  try {
    Write-Host "Downloading via HttpClient: $url"

    # PowerShell 5.x compat: load HttpClient
    if (-not ([System.Management.Automation.PSTypeName]'System.Net.Http.HttpClient').Type) {
      Add-Type -AssemblyName 'System.Net.Http'
    }

    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromMinutes(15)
    $resp = $client.GetAsync($url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
    $resp.EnsureSuccessStatusCode()
    $fs = [System.IO.FileStream]::new($ZIPPATH, [System.IO.FileMode]::Create)
    $resp.Content.CopyToAsync($fs).Wait()
    $fs.Close()
    $client.Dispose()

    if ((Get-Item $ZIPPATH).Length -gt 10MB) { return $true } else { Remove-Item $ZIPPATH -Force }
  } catch {
    Write-Host "Download failed: $($_.Exception.Message)"
    return $false
  }
}

$ok = $false
foreach ($u in $urls) { if (Try-Download $u) { $ok = $true; break } }
if (-not $ok) { throw "Failed to download Neo4j ZIP" }

# --- 3) Extract & prepare -----------------------------------------------------
Expand-Archive -Path $ZIPPATH -DestinationPath $STAGE -Force

$extracted = Get-ChildItem -Path $STAGE -Directory `
  | Where-Object { $_.Name -like "neo4j-community-*" } `
  | Select-Object -First 1
if (-not $extracted) { throw "Cannot find extracted folder after unzip." }

$prepared = Join-Path $STAGE "neo4j"
if (Test-Path $prepared) { Remove-Item $prepared -Recurse -Force }
Rename-Item -Path $extracted.FullName -NewName "neo4j"

# --- 4) Edit conf safely ------------------------------------------------------
function Set-ContentUtf8NoBom {
  param([string]$Path, [string]$Text)
  $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Text)  # no BOM
  [System.IO.File]::WriteAllBytes($Path, $bytes)
}

$CONF = Join-Path $prepared "conf\neo4j.conf"
if (-not (Test-Path $CONF)) { throw "neo4j.conf not found: $CONF" }

# Normalize line endings
$text = Get-Content -LiteralPath $CONF -Raw
$text = $text -replace "`r?`n", "`r`n"

# Normalize/comment variations → set auth disabled
$pattern = '^[\t ]*#?[\t ]*dbms\.security\.auth_enabled[\t ]*=[\t ]*(true|false)[\t ]*$'
if ($text -match $pattern) {
  $text = [System.Text.RegularExpressions.Regex]::Replace(
    $text, $pattern, 'dbms.security.auth_enabled=false',
    [System.Text.RegularExpressions.RegexOptions]::Multiline
  )
} else {
  if ($text.Length -gt 0 -and $text[-1] -ne "`n") { $text += "`r`n" }
  $text += 'dbms.security.auth_enabled=false' + "`r`n"
}

Set-ContentUtf8NoBom -Path $CONF -Text $text

# --- 5) Move to target (fixed folder name) -----------------------------------
# Ensure parent dir
$TARGET_PARENT = Split-Path $TARGET -Parent
if (-not (Test-Path $TARGET_PARENT)) {
  New-Item -ItemType Directory -Path $TARGET_PARENT | Out-Null
}
# Remove existing target if any
if (Test-Path $TARGET) { Remove-Item $TARGET -Recurse -Force }

# Move and correct name
Move-Item -LiteralPath $prepared -Destination $TARGET_PARENT -Force
$justMoved = Join-Path $TARGET_PARENT 'neo4j'
if ((Split-Path $TARGET -Leaf) -ne 'neo4j') {
  if (Test-Path $justMoved) {
    Rename-Item -Path $justMoved -NewName (Split-Path $TARGET -Leaf) -ErrorAction SilentlyContinue
  }
}

# Cleanup stage
Remove-Item $STAGE -Recurse -Force

Write-Host "✅ Neo4j $Version is ready"
Write-Host "📂 Path: $TARGET"
Write-Host "🛠️ conf updated: $CONF"
```
</details> 

<details> <summary><strong>Git Bash (Windows)</strong></summary>

```bash
#!/usr/bin/env bash
# Neo4j Community automatic installer (Git Bash / Windows)
# - Run from repository root (where backend/ is visible) or from backend/
# - Auto-detect latest → download ZIP → unzip → set conf (auth disabled)

set -euo pipefail

VERSION="${VERSION:-latest}"   # e.g., VERSION=5.26.12 ./install_neo4j_gitbash.sh
die(){ echo "Error: $*" >&2; exit 1; }

# Working directory rules
CWD="$(pwd)"
if [[ "$(basename "$CWD")" == "backend" ]]; then
  ROOT="$(dirname "$CWD")"; BACKEND="$CWD"; TARGET="$CWD/neo4j"
elif [[ -d "$CWD/backend" ]]; then
  ROOT="$CWD"; BACKEND="$ROOT/backend"; TARGET="$BACKEND/neo4j"
else
  die "Run from repo root (where backend is visible) or from backend/."
fi
STAGE="$ROOT/neo4j_stage"

# Dependencies
command -v curl >/dev/null || die "curl required"
command -v unzip >/dev/null || die "unzip required"
SED="sed"; command -v gsed >/dev/null && SED="gsed"

# Auto-detect latest version
get_latest_version() {
  local pages=(
    "https://neo4j.com/graph-data-science-software/"
    "https://neo4j.com/deployment-center/"
  )
  local ver=""
  for u in "${pages[@]}"; do
    html="$(curl -fsSL --max-time 30 "$u" || true)"; [[ -z "$html" ]] && continue
    rel="$(printf '%s' "$html" \
      | grep -Eo 'https?://[^"]*download-thanks[^"]+' \
      | grep -E 'edition=community' \
      | grep -E 'flavour=winzip|packaging=zip' \
      | grep -Eo 'release=[0-9]+\.[0-9]+\.[0-9]+' \
      | head -n1 | cut -d= -f2)"
    if [[ -n "$rel" ]]; then ver="$rel"; break; fi
    rel="$(printf '%s' "$html" \
      | grep -Eo 'Neo4j Community Edition[[:space:]]+[0-9]+\.[0-9]+\.[0-9]+' \
      | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
    [[ -n "$rel" ]] && { ver="$rel"; break; }
  done
  [[ -z "$ver" ]] && die "Failed to detect latest version. Set VERSION env var."
  printf '%s' "$ver"
}
[[ "$VERSION" == "latest" ]] && VERSION="$(get_latest_version)"
echo "Using Neo4j Community version: $VERSION"

ZIP="neo4j-community-$VERSION-windows.zip"
URLS=(
  "https://dist.neo4j.org/$ZIP"
  "https://neo4j.com/artifact.php?name=$ZIP"
)

rm -rf "$STAGE"; mkdir -p "$STAGE" "$BACKEND"
ARCHIVE="$STAGE/$ZIP"

download() {
  local url="$1"
  echo "Downloading: $url"
  curl -fL --retry 5 --retry-delay 2 \
       --connect-timeout 25 --max-time 1800 \
       --speed-time 30 --speed-limit 10240 \
       -o "$ARCHIVE" "$url"
}
ok=0
for u in "${URLS[@]}"; do
  if download "$u"; then
    sz="$(wc -c <"$ARCHIVE" 2>/dev/null || echo 0)"
    if [[ "$sz" -gt $((10*1024*1024)) ]]; then ok=1; break; else rm -f "$ARCHIVE"; fi
  fi
done
[[ $ok -eq 1 ]] || die "Neo4j ZIP download failed"

unzip -q "$ARCHIVE" -d "$STAGE"
extracted="$(find "$STAGE" -maxdepth 1 -type d -name 'neo4j-community-*' | head -n1)"
[[ -n "$extracted" ]] || die "Cannot find extracted folder"

prepared="$STAGE/neo4j"
rm -rf "$prepared"; mv "$extracted" "$prepared"

CONF="$prepared/conf/neo4j.conf"
[[ -f "$CONF" ]] || die "neo4j.conf not found: $CONF"

# Normalize and disable auth
if grep -Eq '^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=' "$CONF"; then
  "$SED" -i -E 's/^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=[[:space:]]*(true|false)[[:space:]]*$/dbms.security.auth_enabled=false/' "$CONF"
else
  printf '\n%s\n' 'dbms.security.auth_enabled=false' >> "$CONF"
fi

mkdir -p "$(dirname "$TARGET")"
rm -rf "$TARGET"
mv "$prepared" "$(dirname "$TARGET")"
if [[ "$(basename "$TARGET")" != "neo4j" && -d "$(dirname "$TARGET")/neo4j" ]]; then
  mv "$(dirname "$TARGET")/neo4j" "$TARGET"
fi

rm -rf "$STAGE"
echo "✅ Neo4j $VERSION is ready"
echo "📂 Path: $TARGET"
echo "🛠️ conf updated: $CONF"
```

</details> 

<details><summary><strong>macOS / Linux</strong></summary>

```bash
#!/usr/bin/env bash
# Neo4j Community automatic installer (macOS / Linux)
# - Run from repository root (where backend/ is visible) or from backend/
# - Auto-detect latest → download TAR.GZ → extract → set conf (auth disabled)

set -euo pipefail

VERSION="${VERSION:-latest}"   # e.g., VERSION=5.26.12 ./install_neo4j_macos.sh
die(){ echo "Error: $*" >&2; exit 1; }

# Working directory rules
CWD="$(pwd)"
if [[ "$(basename "$CWD")" == "backend" ]]; then
  ROOT="$(dirname "$CWD")"; BACKEND="$CWD"; TARGET="$CWD/neo4j"
elif [[ -d "$CWD/backend" ]]; then
  ROOT="$CWD"; BACKEND="$ROOT/backend"; TARGET="$BACKEND/neo4j"
else
  die "Run from repo root (where backend is visible) or from backend/."
fi
STAGE="$ROOT/neo4j_stage"

# Dependencies
command -v curl >/dev/null || die "curl required"
command -v tar  >/dev/null || die "tar required"
SED="sed"; command -v gsed >/dev/null && SED="gsed"

# Auto-detect latest version
get_latest_version() {
  local pages=(
    "https://neo4j.com/graph-data-science-software/"
    "https://neo4j.com/deployment-center/"
  )
  local ver=""
  for u in "${pages[@]}"; do
    html="$(curl -fsSL --max-time 30 "$u" || true)"; [[ -z "$html" ]] && continue
    rel="$(printf '%s' "$html" \
      | grep -Eo 'https?://[^"]*download-thanks[^"]+' \
      | grep -E 'edition=community' \
      | grep -E 'unix|packaging=tar(\.gz)?|packaging=zip' \
      | grep -Eo 'release=[0-9]+\.[0-9]+\.[0-9]+' \
      | head -n1 | cut -d= -f2)"
    if [[ -n "$rel" ]]; then ver="$rel"; break; fi
    rel="$(printf '%s' "$html" \
      | grep -Eo 'Neo4j Community Edition[[:space:]]+[0-9]+\.[0-9]+\.[0-9]+' \
      | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
    [[ -n "$rel" ]] && { ver="$rel"; break; }
  done
  [[ -z "$ver" ]] && die "Failed to detect latest version. Set VERSION env var."
  printf '%s' "$ver"
}
[[ "$VERSION" == "latest" ]] && VERSION="$(get_latest_version)"
echo "Using Neo4j Community version: $VERSION"

TAR="neo4j-community-$VERSION-unix.tar.gz"
URLS=(
  "https://dist.neo4j.org/$TAR"
  "https://neo4j.com/artifact.php?name=$TAR"
)

rm -rf "$STAGE"; mkdir -p "$STAGE" "$BACKEND"
ARCHIVE="$STAGE/$TAR"

download() {
  local url="$1"
  echo "Downloading: $url"
  curl -fL --retry 5 --retry-delay 2 \
       --connect-timeout 25 --max-time 1800 \
       --speed-time 30 --speed-limit 10240 \
       -o "$ARCHIVE" "$url"
}
ok=0
for u in "${URLS[@]}"; do
  if download "$u"; then
    sz="$(wc -c <"$ARCHIVE" 2>/dev/null || echo 0)"
    if [[ "$sz" -gt $((10*1024*1024)) ]]; then ok=1; break; else rm -f "$ARCHIVE"; fi
  fi
done
[[ $ok -eq 1 ]] || die "Neo4j tarball download failed"

tar -xzf "$ARCHIVE" -C "$STAGE"
extracted="$(find "$STAGE" -maxdepth 1 -type d -name 'neo4j-community-*' | head -n1)"
[[ -n "$extracted" ]] || die "Cannot find extracted folder"

prepared="$STAGE/neo4j"
rm -rf "$prepared"; mv "$extracted" "$prepared"

CONF="$prepared/conf/neo4j.conf"
[[ -f "$CONF" ]] || die "neo4j.conf not found: $CONF"

# Normalize and disable auth (BSD sed on mac supported)
if grep -Eq '^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=' "$CONF"; then
  if sed --version >/dev/null 2>&1; then
    sed -i -E 's/^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=[[:space:]]*(true|false)[[:space:]]*$/dbms.security.auth_enabled=false/' "$CONF"
  else
    sed -i '' -E 's/^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=[[:space:]]*(true|false)[[:space:]]*$/dbms.security.auth_enabled=false/' "$CONF"
  fi
else
  printf '\n%s\n' 'dbms.security.auth_enabled=false' >> "$CONF"
fi

mkdir -p "$(dirname "$TARGET")"
rm -rf "$TARGET"
mv "$prepared" "$(dirname "$TARGET")"
if [[ "$(basename "$TARGET")" != "neo4j" && -d "$(dirname "$TARGET")/neo4j" ]]; then
  mv "$(dirname "$TARGET")/neo4j" "$TARGET"
fi

rm -rf "$STAGE"
echo "✅ Neo4j $VERSION is ready"
echo "📂 Path: $TARGET"
echo "🛠️ conf updated: $CONF"
```
</details>

#### 2.2.2 Set up Ollama (local AI model)

[Download Ollama](https://ollama.com/download)

#### 2.2.3 Run the backend

```bash
cd backend
python main.py
```

### 2.3 Frontend Setup

#### 2.3.1 Install dependencies

```bash
cd frontend
npm install
```

#### 2.3.2 Run the frontend

```bash
npm run dev
```



## Access Information

| Service            | URL                        | Description               |
| ------------------ | -------------------------- | ------------------------- |
| **Frontend**       | http://localhost:5173      | Main web application      |
| **Backend API**    | http://localhost:8000      | REST API server           |
| **Swagger Docs**   | http://localhost:8000/docs | API documentation & test  |
| **Neo4j Browser**  | http://localhost:7474      | Graph database console    |
| **Ollama API**     | http://localhost:11434     | Local AI model API        |

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
3. Participate in code review and testing

## Support

If you run into problems or need help:

- Open an issue on [GitHub Issues](https://github.com/OSSBrainTrace/BrainTrace/issues)
- Refer to the project documentation
- Use the community forum(s)

---

**Note**: Downloading AI models may require substantial disk space. Allocate up to 10GB per model file.
