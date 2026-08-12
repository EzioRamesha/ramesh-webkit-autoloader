#!/usr/bin/env bash
# Download payload mirrors for Ramesh WebKit Autoloader.
#
# 1) Always refresh latest EchoStretch kstuff-lite + itsPLK pldmgr (homescreen chain).
# 2) Keep pinned ps5-unified-autoloader as payloads/payload.elf for PC-host
#    first-install override compatibility (installer ELF replaces it at host build).
#
# Uses only python3. The Makefile runs this as payload-deps.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="$ROOT/frontend/autoloader/payloads"
mkdir -p "$DEST_DIR"

python3 - "$DEST_DIR" <<'PY'
import hashlib, json, os, sys, urllib.request

dest_dir = sys.argv[1]

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ramesh-webkit-autoloader-build"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def write_elf(path, data, tag):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    with open(path + ".sha256", "w") as f:
        f.write(f"{tag} {sha256(data)}\n")
    print(f"ready: {path} ({tag}, {len(data)} bytes, sha256={sha256(data)[:12]}…)")

# --- kstuff-lite: always latest ---
k_meta = json.loads(fetch("https://api.github.com/repos/EchoStretch/kstuff-lite/releases/latest"))
k_tag = k_meta.get("tag_name", "latest")
k_asset = None
for a in k_meta.get("assets", []):
    if a.get("name") == "kstuff.elf" or str(a.get("name", "")).endswith(".elf"):
        k_asset = a
        break
if not k_asset:
    sys.exit("Error: kstuff-lite latest release has no ELF asset")
print(f"Fetching EchoStretch/kstuff-lite@{k_tag} → kstuff-lite.elf …")
write_elf(os.path.join(dest_dir, "kstuff-lite.elf"), fetch(k_asset["browser_download_url"]), k_tag)

# --- pldmgr: always latest ---
p_meta = json.loads(fetch("https://api.github.com/repos/itsPLK/ps5-payload-manager/releases/latest"))
p_tag = p_meta.get("tag_name", "latest")
p_asset = None
for a in p_meta.get("assets", []):
    name = a.get("name", "")
    if name.startswith("pldmgr") and name.endswith(".elf"):
        p_asset = a
        break
if not p_asset:
    sys.exit("Error: ps5-payload-manager latest release has no pldmgr*.elf")
print(f"Fetching itsPLK/ps5-payload-manager@{p_tag} → pldmgr.elf …")
write_elf(os.path.join(dest_dir, "pldmgr.elf"), fetch(p_asset["browser_download_url"]), p_tag)

print("Ramesh chain mirrors updated (kstuff-lite + pldmgr).")
PY

# Keep original unified-autoloader payload.elf for host-build compatibility.
SUBMODULE="$ROOT/third_party/ps5-unified-autoloader"
DEST="$DEST_DIR/payload.elf"
REPO="itsPLK/ps5-unified-autoloader"

if [ ! -e "$SUBMODULE/.git" ]; then
    echo "Error: ps5-unified-autoloader submodule is not initialised."
    echo "Run: git submodule update --init --recursive"
    exit 1
fi

TAG=$(git -C "$SUBMODULE" describe --tags --always)

python3 - "$REPO" "$TAG" "$DEST" <<'PY'
import hashlib, json, os, sys, urllib.request
repo, tag, dest = sys.argv[1], sys.argv[2], sys.argv[3]
sidecar = dest + ".sha256"

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

if os.path.isfile(dest) and os.path.isfile(sidecar):
    with open(sidecar) as f:
        try:
            st_tag, st_hash = f.read().split()
        except ValueError:
            st_tag, st_hash = "", ""
    if st_tag == tag and sha256_of(dest) == st_hash:
        print(f"ps5-unified-autoloader payload already present and verified ({tag}).")
        sys.exit(0)

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ramesh-webkit-autoloader-build"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()

try:
    release = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/tags/{tag}"))
except Exception as exc:
    # Fallback: latest if pinned tag missing
    print(f"Warn: tag {tag} fetch failed ({exc}); trying latest…")
    release = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/latest"))
    tag = release.get("tag_name", tag)

asset = None
for a in release.get("assets", []):
    if a.get("name", "").endswith(".elf"):
        asset = a
        break
if asset is None:
    print(f"Error: release {tag} has no .elf asset.", file=sys.stderr)
    sys.exit(1)

digest = asset.get("digest", "")
digest = digest.split(":", 1)[-1] if ":" in digest else digest
url = asset["browser_download_url"]
print(f"Downloading {url} …")
os.makedirs(os.path.dirname(dest), exist_ok=True)
data = fetch(url)
if digest:
    actual = hashlib.sha256(data).hexdigest()
    if actual != digest:
        print(f"Error: sha256 mismatch (got {actual}, expected {digest}).", file=sys.stderr)
        sys.exit(1)
tmp = dest + ".tmp"
with open(tmp, "wb") as f:
    f.write(data)
os.replace(tmp, dest)
with open(sidecar, "w") as f:
    f.write(f"{tag} {digest or hashlib.sha256(data).hexdigest()}\n")
print(f"ps5-unified-autoloader payload ready ({tag}): {dest}")
PY
