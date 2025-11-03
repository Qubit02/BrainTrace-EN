# BrainTrace Execution Guide

> **BrainTrace** is a knowledge‑graph‑based AI‑chatbot system that automatically builds a knowledge graph from uploaded documents and generates accurate answers.

## Table of Contents

- [System Requirements](#system-requirements)
- [Detailed Installation Guide](#detailed-installation-guide)
- [Access Information](#access-information)
- [Additional Resources](#additional-resources)
- [Contributing](#contributing)
- [Support](#support)

## System Requirements <a id="system-requirements"></a>

### Basic Requirements

- **Operating System**: Windows 10/11  
- **Python**: 3.12  
- **Node.js**: 20.19.0 or higher  
- **Neo4j**: see below  
- **Ollama**: see below  

### Hardware Requirements

#### Profile A: External LLM / No Local LLM

| Profile | CPU | RAM | Disk |
| --- | --- | --- | --- |
| **A) External LLM / No Local LLM** | 2–4 cores | **≥ 8 GB** | 10–20 GB |
| **B) Local LLM (Ollama 7B, Q4)** | 4–8 cores | **Min 12 GB (16 GB recommended)** | 30–50 GB+ (model/cache) |

**Recommended Specs**

- CPU: 6 cores  
- Memory: 16 GB RAM  
- Storage: 50 GB+ free space (AI models & database)

## Detailed Installation Guide (Bare‑metal run, or choose [Run with Docker](#run-with-docker)) <a id="detailed-installation-guide"></a>

### 1. Bare‑metal Run

```bash
git clone https://github.com/Qubit02/BrainTrace.git
cd BrainTrace
```

### 1.1 Backend Setup

#### 1.1.1 Create & activate Python venv (start in BrainTrace/)

```bash
cd backend

# Create virtual environment
python -m venv venv
```

#### Activate venv

```
# Windows
venv\Scripts\activate
```

```
# macOS/Linux
source venv/bin/activate
```

#### 1.1.2 Install dependencies

```bash
pip install -r requirements.txt
```

#### 1.1.3 Set environment variables

```bash
# Create .env  → backend/.env

# Path for local Ollama models
OLLAMA_MODELS=./models/ollama

# API key
# OPENAI_API_KEY=your_api_key_here
```

### 1.2 Database Setup

#### 1.2.1 Install Neo4j

> The scripts below automatically detect the working directory.  
> Run them from the **repository root (BrainTrace/)** or from inside **backend/**.

#### Windows installation (PowerShell or Git Bash — copy the snippet for your shell)

<details>
<summary><strong>PowerShell (Windows)</strong></summary>

```powershell
( set -eu
  set +u; set -o pipefail 2>/dev/null || true; set -u

  : "${VERSION:=latest}"

  CWD="$PWD"
  if [[ "$(basename "$CWD")" == "backend" ]]; then
    ROOT="$(dirname "$CWD")"; BACKEND="$CWD"; TARGET="$BACKEND/neo4j"
  elif [[ -d "$CWD/backend" ]]; then
    ROOT="$CWD"; BACKEND="$ROOT/backend"; TARGET="$BACKEND/neo4j"
  else
    echo "❌ Do not run here. Execute from the repository root (where the backend folder is visible) or inside backend/." >&2
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
    echo "🌐 Checking latest version..."
    if ! VERSION="$(get_latest_version)"; then
      echo "❌ Failed to detect latest version. Specify VERSION env var. (e.g., export VERSION=5.26.12)" >&2
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
  [[ $ok -eq 1 ]] || { echo "❌ Neo4j tarball download failed" >&2; exit 1; }

  tar -xzf "$ARCHIVE" -C "$STAGE"
  extracted="$(find "$STAGE" -maxdepth 1 -type d -name 'neo4j-community-*' | head -n1)"
  [[ -n "$extracted" ]] || { echo "❌ Cannot find folder after extraction" >&2; exit 1; }

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
  echo "✅ Neo4j $VERSION ready"
  echo "📂 Path: $TARGET"
  echo "🛠️ Conf: $CONF"
  echo "🚀 Run:  $TARGET/bin/neo4j console"
)

```
</details>

<details><summary><strong>Git Bash (Windows)</strong></summary>

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
    echo "❌ Do not run here. Execute from the repository root (where the backend folder is visible) or inside backend/." >&2
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
    echo "🌐 Checking latest version..."
    if ! VERSION="$(get_latest_version)"; then
      echo "❌ Failed to detect latest version. Specify VERSION env var. (e.g., export VERSION=5.26.12)" >&2
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
  [[ $ok -eq 1 ]] || { echo "❌ Neo4j tarball download failed" >&2; exit 1; }

  tar -xzf "$ARCHIVE" -C "$STAGE"
  extracted="$(find "$STAGE" -maxdepth 1 -type d -name 'neo4j-community-*' | head -n1)"
  [[ -n "$extracted" ]] || { echo "❌ Cannot find folder after extraction" >&2; exit 1; }

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
  echo "✅ Neo4j $VERSION ready"
  echo "📂 Path: $TARGET"
  echo "🛠️ Conf: $CONF"
  echo "🚀 Run:  $TARGET/bin/neo4j console"
)

```
</details>

#### macOS / Linux installation

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
    echo "❌ Do not run here. Execute from the repository root (where the backend folder is visible) or inside backend/." >&2
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
    echo "🌐 Checking latest version..."
    if ! VERSION="$(get_latest_version)"; then
      echo "❌ Failed to detect latest version. Specify VERSION env var. (e.g., export VERSION=5.26.12)" >&2
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
  [[ $ok -eq 1 ]] || { echo "❌ Neo4j tarball download failed" >&2; exit 1; }

  tar -xzf "$ARCHIVE" -C "$STAGE"
  extracted="$(find "$STAGE" -maxdepth 1 -type d -name 'neo4j-community-*' | head -n1)"
  [[ -n "$extracted" ]] || { echo "❌ Cannot find folder after extraction" >&2; exit 1; }

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
  echo "✅ Neo4j $VERSION ready"
  echo "📂 Path: $TARGET"
  echo "🛠️ Conf: $CONF"
  echo "🚀 Run:  $TARGET/bin/neo4j console"
)

```
</details>

#### 1.2.2 Ollama setup (local AI model)

[Download Ollama](https://ollama.com/download)

#### 1.2.3 Start the backend

```bash
py main.py
```

### 1.3 Frontend Run

#### 1.3.1 Install dependencies (start in BrainTrace/)

```bash
cd frontend
npm install
```

#### 1.3.2 Run frontend

```bash
npm run dev
```

---

### 2. Run with Docker <a id="run-with-docker"></a>

```bash
# Clone the repository
git clone https://github.com/Qubit02/BrainTrace.git
cd BrainTrace

# Launch with Docker Compose
docker-compose up -d

# Open in browser
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000
# Neo4j: http://localhost:7474
```

### Run the entire stack

```bash
docker-compose up -d
```

### Run individual services

```bash
docker-compose up backend    # Backend only
docker-compose up frontend   # Frontend only
docker-compose up neo4j ollama   # Neo4j & Ollama
```

### Stop & clean up

```bash
docker-compose down          # Stop services
docker-compose down -v       # Remove volumes
docker-compose build --no-cache   # Rebuild images
```

## Access Information <a id="access-information"></a>

| Service | URL | Description |
| ------- | --- | ----------- |
| **Frontend** | http://localhost:5173 | Main web application |
| **Backend API** | http://localhost:8000 | REST API server |
| **Swagger Docs** | http://localhost:8000/docs | API documentation & testing |
| **Neo4j Browser** | http://localhost:7474 | Graph database UI |
| **Ollama API** | http://localhost:11434 | Local AI model API |

## Additional Resources <a id="additional-resources"></a>

- [Project README](./README.md)
- [Knowledge Graph Documentation](./KNOWLEDGE_GRAPH.md)
- [API Documentation](http://localhost:8000/docs)
- [Neo4j Documentation](https://neo4j.com/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Contributing <a id="contributing"></a>

Want to contribute?

1. Open an issue to propose a bug fix or feature.  
2. Fork the repo and submit a Pull Request.  
3. Participate in code review & testing.  

## Support <a id="support"></a>

Need help?

- Create a [GitHub Issue](https://github.com/OSSBrainTrace/BrainTrace/issues)
- Check the project docs
- Use the community forum

---

**Note**: Downloading AI models may consume significant disk space — up to 10 GB per model file.
