#!/usr/bin/env bash
# Prepare the slopkit copy used by the frontend and apply our autoloader patch.
#
# slopkit lives as a pristine git submodule in third_party/slopkit (never
# modified). The frontend needs it under frontend/autoloader/slopkit, so this
# script:
#   1. copies third_party/slopkit -> frontend/autoloader/slopkit (fresh copy)
#   2. applies tools/slopkit-autoload.patch to the copy
#
# The copy is gitignored (frontend/autoloader/slopkit/), so the submodule is
# never dirtied. Run after every submodule update:
#
#   git submodule update --init --recursive
#   tools/apply_slopkit_patch.sh
#
# The Makefile runs this automatically before staging/serving (slopkit-prepare).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/third_party/slopkit"
DEST="$ROOT/frontend/autoloader/slopkit"
PATCH="$ROOT/tools/slopkit-autoload.patch"

if [ ! -e "$SOURCE/.git" ]; then
    echo "Error: slopkit submodule is not initialised."
    echo "Run: git submodule update --init --recursive"
    exit 1
fi

if [ ! -f "$PATCH" ]; then
    echo "Error: patch file not found: $PATCH"
    exit 1
fi

# 1. Fresh copy (drop .git, .github, anything not needed at runtime)
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$SOURCE"/. "$DEST"/
rm -rf "$DEST/.git" "$DEST/.github" "$DEST/.gitignore" "$DEST/.gitmodules"

# 2. Turn the copy into a throwaway git repo so `git apply` can handle binary
#    diffs (e.g. the deleted cat gif) — plain git apply on a non-repo dir
#    cannot. Two commits: pristine slopkit, then our autoloader patch.
SRC_HASH=$(git -C "$SOURCE" rev-parse --short HEAD)
git -C "$DEST" init -q
git -C "$DEST" config user.name "wkal"
git -C "$DEST" config user.email "wkal@localhost"
git -C "$DEST" add -A
git -C "$DEST" commit -q -m "slopkit pristine (submodule $SRC_HASH)"

# 3. Apply the patch
cd "$DEST"
if git apply --check "$PATCH" 2>/dev/null; then
    git apply "$PATCH"
    git add -A
    git commit -q -m "Apply WKAL autoloader patch"
    echo "slopkit: copied to $DEST and autoloader patch applied."
elif git apply --reverse --check "$PATCH" 2>/dev/null; then
    echo "slopkit: autoloader patch is already applied."
else
    echo "Error: patch does not apply cleanly to $DEST."
    echo "slopkit has likely changed upstream — regenerate tools/slopkit-autoload.patch:"
    echo "  git -C $SOURCE diff > $PATCH"
    exit 1
fi

# 3b. Ramesh fork: kstuff-lite → pldmgr (latest + local fallback)
python3 "$ROOT/tools/inject_ramesh_chain.py"
git -C "$DEST" add -A
git -C "$DEST" commit -q -m "Apply Ramesh kstuff→pldmgr chain" || true

# 3c. Iris continue-JB: skip kernel ladder when elfldr already listens
python3 "$ROOT/tools/inject_continue_guard.py"
git -C "$DEST" add -A
git -C "$DEST" commit -q -m "Apply Iris continue-JB guard" || true

# 4. Sanity check: the patched page must carry our integration markers and the
#    big cat gif must be gone. Catches a silently truncated/empty patch.
if ! grep -q 'autoload: Q.get("autoload")' slopkit/poops.html \
    || ! grep -q 'PAYLOAD_MAX_SIZE = 0x400000' slopkit/poops.html \
    || ! grep -q 'Ramesh chain: kstuff-lite then pldmgr' slopkit/poops.html \
    || ! grep -q 'Iris chain payloads' slopkit/poops.html \
    || ! grep -q 'data-name="kstuff-lite.elf"' slopkit/poops.html \
    || ! grep -q 'CONTINUE-OK' slopkit/poops.html \
    || ! grep -q 'probeElfldrListening' slopkit/poops.html \
    || [ -f slopkit/mmhmm-cats-ps5.gif ]; then
    echo "Error: slopkit patch verification FAILED — integration markers missing."
    echo "tools/slopkit-autoload.patch is incomplete or out of date."
    echo "Regenerate it from the pristine submodule:"
    echo "  git -C $SOURCE diff > $PATCH"
    exit 1
fi
echo "slopkit: patch verification OK (autoload, Ramesh chain, continue-JB, 4 MiB limit, cat gif removed)."
