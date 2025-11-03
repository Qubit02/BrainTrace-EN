# BrainTrace Execution Guide

> **BrainTrace** is a knowledge‑graph‑based AI chatbot system that automatically builds a knowledge graph from uploaded documents and generates accurate answers.

## Table of Contents

- [System Requirements](#시스템-요구사항)
- [Detailed Installation Guide](#상세-설치-가이드)
- [Access Information](#접속-정보)
- [Additional Resources](#추가-리소스)

## System Requirements

### Basic Requirements

- **Operating System**: Windows 10/11
- **Python**: 3.12
- **Node.js**: 20.19.0 or higher
- **Neo4j**: see below
- **Ollama**: see below

### Hardware Requirements

#### Profile A: External LLM / No Local LLM

| Profile | CPU | RAM | Disk |
| ----------------------------------------- | ------- | ------------------------- | --------------------- |
| **A) External LLM / No Local LLM** | 2–4 cores | **≥ 8GB** | 10–20GB |
| **B) Local LLM (Ollama 7B, Q4)** | 4–8 cores | **Min 12GB (16GB recommended)** | 30–50GB+ (models/cache) |

**Recommended Specs**

- CPU: 6 cores
- Memory: 16GB RAM
- Storage: 50GB+ free space (for AI models and database)


## Detailed Installation Guide (Bare‑metal run, choose this or [Run with Docker](#도커로-실행)) <a id="상세-설치-가이드"></a>

### 1. Bare‑metal Run

```bash
git clone https://github.com/Qubit02/BrainTrace.git
cd BrainTrace
```

### 1.1 백엔드 설정

#### 1.1.1 Create and activate Python venv (start in BrainTrace/)

```bash
cd backend

# 가상환경 생성
python -m venv venv
```

#### Activate venv

```
# Windows
venv\Scripts\activate
```

```
# macOS/Linux
source venv/bin/activate
```

#### 1.1.2 Install dependencies

```bash
pip install -r requirements.txt
```

#### 1.1.3 Set environment variables

```bash
# .env 파일 생성 -> backend/.env

#Ollama 사용 시 모델 설치 위치 변수 추가
OLLAMA_MODELS=./models/ollama

# API 키 입력
# OPENAI_API_KEY=your_api_key_here
```

### 1.2 Database Setup

#### 1.2.1 Install Neo4j

> The scripts below auto‑detect the working directory. Run them either from the **repository root (BrainTrace/)** or inside **backend/**.

#### Windows installation (PowerShell or Git Bash – copy the snippet for your shell)

<details>
<summary><strong>PowerShell (Windows)</strong></summary>
  
```powershell
param(
  [string]$Version = 'latest'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --- 0) 설정 & 경로 규칙 -----------------------------------------------------
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
  throw "여기서는 실행하지 마세요. 루트(backend 폴더가 보이는 곳) 또는 backend 폴더에서 실행하세요."
}

$STAGE  = Join-Path $ROOT 'neo4j_stage'

if (-not ([Net.ServicePointManager]::SecurityProtocol -band [Net.SecurityProtocolType]::Tls12)) {
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

# --- 1) 최신 버전 자동 탐지 ---------------------------------------------------
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

  throw "최신 버전을 찾지 못했습니다. -Version '5.26.12' 같은 식으로 지정하세요."
}

if ($Version -eq 'latest') { $Version = Get-LatestNeo4jVersion }
Write-Host "Using Neo4j Community version: $Version"

# --- 2) 다운로드 --------------------------------------------------------------
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
if (-not $ok) { throw "Neo4j ZIP 다운로드 실패" }

# --- 3) 압축 해제 & 폴더 정리 ------------------------------------------------
Expand-Archive -Path $ZIPPATH -DestinationPath $STAGE -Force

$extracted = Get-ChildItem -Path $STAGE -Directory |
  Where-Object { $_.Name -like "neo4j-community-*" } |
  Select-Object -First 1
if (-not $extracted) { throw "압축 해제 후 폴더를 찾을 수 없습니다." }

$prepared = Join-Path $STAGE "neo4j"
if (Test-Path $prepared) { Remove-Item $prepared -Recurse -Force }
Rename-Item -Path $extracted.FullName -NewName "neo4j"

# --- 4) 대상 위치로 이동 (폴더명 고정) ---------------------------------------
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

# --- 5) conf 수정 (최종 경로 기준으로) ---------------------------------------
$CONF = Join-Path $TARGET 'conf\neo4j.conf'
if (-not (Test-Path $CONF)) { throw "neo4j.conf not found: $CONF" }

$text = Get-Content -LiteralPath $CONF -Raw
$text = $text -replace "`r?`n", "`r`n"

$pattern = '^[\t ]*#?[\t ]*dbms\.security\.auth_enabled[\t ]*=[\t ]*(true|false)([\t ]*#.*)?$'
if ($text -match $pattern) {
  $text = [Regex]::Replace($text, $pattern, 'dbms.security.auth_enabled=false',
    [System.Text.RegularExpressions.RegexOptions]::Multiline)
} else {
  if ($text.Length -gt 0 -and $text[-1] -ne "`n") { $text += "`r`n" }
  $text += 'dbms.security.auth_enabled=false' + "`r`n"
}

$bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($text)
[System.IO.File]::WriteAllBytes($CONF, $bytes)

# --- 6) Stage 정리 & 결과 표시 ------------------------------------------------
Remove-Item $STAGE -Recurse -Force

Write-Host "✅ Neo4j $Version 준비 완료"
```
</details> 

<details> <summary><strong>Git Bash (Windows)</strong></summary>

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-latest}"

# ── 0) 경로 규칙 ──────────────────────────────────────────────
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
  echo "❌ backend 폴더가 보이는 루트나 backend 내부에서 실행하세요." >&2
  exit 1
fi
STAGE="$ROOT/neo4j_stage"

mkdir -p "$STAGE" "$BACKEND"

# ── 1) 최신 버전 자동 탐지 ───────────────────────────────────
if [[ "$VERSION" == "latest" ]]; then
  echo "🔍 Fetching latest Neo4j Community version..."
  VERSION="$(curl -fsSL https://dist.neo4j.org/ | \
             grep -Eo 'neo4j-community-[0-9.]+-windows.zip' | \
             sort -V | tail -1 | grep -Eo '[0-9.]+')" || true
  [[ -z "$VERSION" ]] && VERSION="5.26.12"
fi
echo "Using Neo4j Community version: $VERSION"

# ── 2) 다운로드 ───────────────────────────────────────────────
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

[[ ! -s "$ZIPFILE" ]] && { echo "❌ 다운로드 실패"; exit 1; }

# ── 3) 압축 해제 및 폴더 정리 ────────────────────────────────
unzip -q -o "$ZIPFILE"
EXTRACTED="$(find . -maxdepth 1 -type d -name "neo4j-community-*")"
[[ -z "$EXTRACTED" ]] && { echo "❌ 압축 해제 실패"; exit 1; }
rm -rf neo4j && mv "$EXTRACTED" neo4j

# ── 4) 대상 위치로 이동 ───────────────────────────────────────
rm -rf "$TARGET"
mkdir -p "$(dirname "$TARGET")"
mv neo4j "$TARGET"

# ── 5) conf 수정 (v4/v5 호환) ────────────────────────────────
CONF="$TARGET/conf/neo4j.conf"
[[ ! -f "$CONF" ]] && { echo "❌ conf 파일 없음: $CONF"; exit 1; }

# 줄 통일 후 키 처리
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

# ── 6) 정리 및 출력 ───────────────────────────────────────────
rm -rf "$STAGE"
echo "✅ Neo4j $VERSION 설치 완료"
```
</details>


#### macOS / Linux installation

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
  else
    echo "❌ 여기서는 실행하지 마세요. 루트(backend 폴더 보이는 위치) 또는 backend/ 에서 실행" >&2
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
      rel="$(printf '%s' "$html" \
        | grep -Eo 'https?://[^"]*download-thanks[^"]+' \
        | grep -E 'edition=community' \
        | grep -E 'unix|packaging=tar(\.gz)?|packaging=zip' \
        | grep -Eo 'release=[0-9]+\.[0-9]+\.[0-9]+' \
        | head -n1 | cut -d= -f2)"
      [[ -n "$rel" ]] && { printf '%s' "$rel"; return 0; }
      rel="$(printf '%s' "$html" \
        | grep -Eo 'Neo4j Community Edition[[:space:]]+[0-9]+\.[0-9]+\.[0-9]+' \
        | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' \
        | head -n1)"
      [[ -n "$rel" ]] && { printf '%s' "$rel"; return 0; }
    done
    return 1
  }

  if [[ "$VERSION" == "latest" ]]; then
    echo "🌐 최신 버전 확인 중..."
    if ! VERSION="$(get_latest_version)"; then
      echo "❌ 최신 버전 탐지 실패. 환경변수 VERSION으로 지정하세요. (예: export VERSION=5.26.12)" >&2
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
  [[ $ok -eq 1 ]] || { echo "❌ Neo4j tarball 다운로드 실패" >&2; exit 1; }

  tar -xzf "$ARCHIVE" -C "$STAGE"
  extracted="$(find "$STAGE" -maxdepth 1 -type d -name 'neo4j-community-*' | head -n1)"
  [[ -n "$extracted" ]] || { echo "❌ 압축 해제 후 폴더를 찾을 수 없습니다." >&2; exit 1; }

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
    if "$SED" -E -n 's/^[[:space:]]*#?[[:space:]]*dbms\.security\.auth_enabled[[:space:]]*=.*/X/p' "$CONF" | grep -q .; then
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
  echo "✅ Neo4j $VERSION 준비 완료"
  echo "📂 경로: $TARGET"
  echo "🛠️ conf 적용: $CONF"
  echo "🚀 실행 예:  $TARGET/bin/neo4j console"
)
```
</details>

#### 1.2.2 Ollama setup (local AI model)

[Ollama 다운로드](https://ollama.com/download)

#### 1.2.3 Start the backend

```bash
py main.py
```

### 1.3 Frontend Setup

#### 1.3.1 Install dependencies (start in BrainTrace/)

```bash
cd frontend
npm install
```

#### 1.3.2 Run frontend

```bash
npm run dev
```
---
### 2. 도커로 실행<a id="도커로-실행"></a>

```bash
# 저장소 클론
git clone https://github.com/Qubit02/BrainTrace.git
cd BrainTrace

# 도커 컴포즈로 실행
docker-compose up -d

# 브라우저에서 접속
# 프론트엔드: http://localhost:5173
# 백엔드 API: http://localhost:8000
# Neo4j: http://localhost:7474
```

### 전체 스택 실행

```bash
# 모든 서비스 실행
docker-compose up -d
```

### 개별 서비스 실행

```bash
# 백엔드만 실행
docker-compose up backend

# 프론트엔드만 실행
docker-compose up frontend

# neo4j/ollama 공식 컨테이너 실행
docker-compose up neo4j ollama
```

### 서비스 중지 및 정리

```bash
# 서비스 중지
docker-compose down

# 볼륨까지 삭제
docker-compose down -v

# 이미지 재빌드
docker-compose build --no-cache
```


## Access Information

| Service            | URL                        | Description              |
| ------------------ | -------------------------- | ------------------------ |
| **Frontend**       | http://localhost:5173      | Main web application     |
| **Backend API**    | http://localhost:8000      | REST API server          |
| **Swagger Docs**   | http://localhost:8000/docs | API documentation & test |
| **Neo4j Browser**  | http://localhost:7474      | Graph database UI        |
| **Ollama API**     | http://localhost:11434     | Local AI model API       |

## Additional Resources

- [프로젝트 README](./README.md)
- [지식 그래프 문서](./KNOWLEDGE_GRAPH.md)
- [API 문서](http://localhost:8000/docs)
- [Neo4j 문서](https://neo4j.com/docs/)
- [FastAPI 문서](https://fastapi.tiangolo.com/)

## Contributing

To contribute to the project:

1. Open an issue to propose bugs or feature requests
2. Fork the repo and submit a Pull Request
3. Participate in code review and testing

## Support

If you encounter issues or need help:

- Create a [GitHub Issue](https://github.com/OSSBrainTrace/BrainTrace/issues)
- Refer to the project documentation
- Use the community forum

---

**Note**: Downloading AI models can require significant disk space—up to 10 GB per model.
