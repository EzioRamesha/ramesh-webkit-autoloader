#!/usr/bin/env python3
"""
Generate a C file registry + cache.appcache manifest from a dist directory.

Scans <dist_dir> recursively and produces:
  - <header_out>  : file_registry.h  (FileEntry struct + extern table)
  - <source_out>  : file_registry.c  (byte arrays + lookup function)
  - <dist_dir>/cache.appcache        (AppCache manifest listing all files)

Usage: gen_file_registry.py <dist_dir> <header_out> <source_out>
"""

import os
import posixpath
import re
import sys
import zlib

from gen_version import get_version_info

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".appcache": "text/cache-manifest",
    ".txt": "text/plain",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
}


def detect_content_type(path):
    ext = os.path.splitext(path)[1].lower()
    return CONTENT_TYPES.get(ext, "application/octet-stream")


# slopkit ships its own payload menu servers (ftpsrv, gdbsrv, kstuff, ...) that
# our autoloader never uses — the chain only needs the elfldr it boots and the
# kexp shellcode that loads it. Skipping the rest keeps the installer ELF ~6 MB
# smaller. readme.png is a slopkit repo asset, also unused. The copied slopkit
# is a throwaway git repo (tools/apply_slopkit_patch.sh), so .git must never
# be embedded. The payload digest sidecar (payloads/*.sha256) is build-time
# bookkeeping and must never be served.
def include_in_registry(path):
    if "/.git/" in path or path.endswith("/.git"):
        return False
    if path.startswith("/app/slopkit/payloads/"):
        return path.endswith(("elfldr-ps5-1360.elf", "kexp_2026_05_25.bin"))
    if path == "/app/slopkit/readme.png":
        return False
    if path.startswith("/app/payloads/") and path.endswith(".sha256"):
        return False
    return True


VERSION_PLACEHOLDER = b"[[VERSION_PLACEHOLDER]]"
BUILD_TIME_PLACEHOLDER = b"[[BUILD_TIME_PLACEHOLDER]]"

# Files that carry the version/badge and get the placeholders replaced:
# installer page at the dist root, and the autoloader app under /app/.
VERSIONED_PATHS = ("/index.html", "/app/index.html")


def apply_version_placeholder(path, data, version, build_time):
    """Replace [[VERSION_PLACEHOLDER]]/[[BUILD_TIME_PLACEHOLDER]] in versioned HTML files."""
    if path in VERSIONED_PATHS:
        data = data.replace(VERSION_PLACEHOLDER, version.encode("utf-8"))
        data = data.replace(BUILD_TIME_PLACEHOLDER, build_time.encode("utf-8"))
    return data


def emit_c_array(out, name, data):
    out.write(f"static const unsigned char {name}[] = {{\n")
    for i in range(0, len(data), 12):
        chunk = ", ".join(f"0x{b:02x}" for b in data[i : i + 12])
        out.write(f"    {chunk},\n")
    out.write("};\n")


# Compress embedded files with raw DEFLATE (no zlib header), matching the
# vendored puff.c inflater in src/inflate.c. This roughly halves the registry
# and keeps the installer ELF small. Files that would not shrink are stored
# uncompressed instead.
def compress_entry(data):
    if len(data) < 64:
        return data, False
    co = zlib.compressobj(level=9, wbits=-15)
    comp = co.compress(data) + co.flush()
    if len(comp) >= len(data):
        return data, False
    return comp, True


# The autoloader iframe loads poops.html with this exact query string. AppCache
# matches URLs exactly (query included), so the manifest must list the full URL
# or the console serves a fallback document instead of the exploit page.
# Keep in sync with EXPLOIT_URL in frontend/autoloader/app.js.
EXPLOIT_IFRAME_URL = (
    "/app/slopkit/slopkit/poops.html"
    "?go=1&auto=1&production=1&trigger=netcontrol&attempts=8"
    "&only=ps0_preflight,ps1_prepare,ps3_stage0,ps4_validate"
    ",ps5_stage1,ps6_stage2,ps8_stage3,ps9_stage4,ps10_stage5"
    "&log=debug&payload=1&autoload=chain&v=42"
)

# slopkit references its own scripts with cache-busting query strings
# (e.g. "./core.js?v=10", "main.js?v=19", "../offsets/9.00.js?v=19").
# AppCache matches URLs exactly, so the manifest must list those query
# variants too or the console falls back and the module imports fail.
CACHEBUST_RE = re.compile(r'([A-Za-z0-9_./-]+\.(?:js|css|html|png|jpg|gif))\?v=\d+')


def collect_cachebust_urls(files):
    """Scan staged HTML/JS for query-string script imports (slopkit's ?v=
    cache-busters) and return their absolute URLs, resolved relative to the
    referencing file. Offsets are loaded dynamically as ../offsets/<fw>.js?v=19
    in main.js, so every offsets file gets the ?v=19 variant as well."""
    urls = set()
    for path, full in files:
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
        except OSError:
            continue
        base = posixpath.dirname(path)
        for match in CACHEBUST_RE.finditer(data):
            ref, query = match.group(1), match.group(0)[len(match.group(1)):]
            resolved = posixpath.normpath(posixpath.join(base, ref))
            if resolved.startswith("/") and "/slopkit/" in resolved:
                urls.add(resolved + query)
    for path, _ in files:
        if path.startswith("/app/slopkit/offsets/") and path.endswith(".js"):
            urls.add(path + "?v=19")
    return sorted(urls)


def build_manifest(files, version, build_time):
    lines = [
        "CACHE MANIFEST",
        f"# WebKit Autoloader v{version} by PLK (built {build_time}) - "
        "auto-generated by tools/gen_file_registry.py, do not edit.",
        "",
        "CACHE:",
    ]
    lines += [path for path, _ in files]
    lines.append(EXPLOIT_IFRAME_URL)
    lines += collect_cachebust_urls(files)
    lines += [
        "",
        "NETWORK:",
        "/cache_complete",
        "/version",
        "",
        "FALLBACK:",
        "/ /index.html",
    ]

    # Fall back to <dir>/index.html for each subdirectory that has one
    # (e.g. "/app/ /app/index.html"), so cached apps work offline.
    paths = {path for path, _ in files}
    for path in sorted(paths):
        if path == "/index.html" or not path.endswith("/index.html"):
            continue
        directory = os.path.dirname(path)
        if directory != "/":
            lines.append(f"{directory}/ {path}")

    lines += [""]
    return "\n".join(lines)


def main():
    if len(sys.argv) != 4:
        print("Usage: gen_file_registry.py <dist_dir> <header_out> <source_out>")
        sys.exit(1)

    dist_dir, header_out, source_out = sys.argv[1:4]

    if not os.path.isdir(dist_dir):
        print(f"Error: {dist_dir} not found or not a directory.")
        sys.exit(1)

    files = []
    for root, dirs, names in os.walk(dist_dir):
        dirs.sort()
        for name in sorted(names):
            if name == "cache.appcache":
                continue  # regenerated below
            full = os.path.join(root, name)
            rel = os.path.relpath(full, dist_dir).replace(os.sep, "/")
            if not include_in_registry(f"/{rel}"):
                continue
            files.append((f"/{rel}", full))
    files.sort(key=lambda f: f[0])

    version_info = get_version_info()

    # Write cache.appcache into the dist dir and include it in the registry
    manifest_path = os.path.join(dist_dir, "cache.appcache")
    with open(manifest_path, "w") as f:
        f.write(build_manifest(files, version_info["full"], version_info["build_time"]))

    files.append((f"/cache.appcache", manifest_path))
    files.sort(key=lambda f: f[0])

    # Header
    with open(header_out, "w") as out:
        out.write("/* Auto-generated by tools/gen_file_registry.py - do not edit. */\n")
        out.write("\n")
        out.write("#ifndef FILE_REGISTRY_H\n")
        out.write("#define FILE_REGISTRY_H\n")
        out.write("\n")
        out.write("typedef struct {\n")
        out.write("    const char *path;\n")
        out.write("    const unsigned char *data;\n")
        out.write("    unsigned int size;\n")
        out.write("    unsigned int orig_size;\n")
        out.write("    unsigned char compressed;\n")
        out.write("    const char *content_type;\n")
        out.write("} FileEntry;\n")
        out.write("\n")
        out.write("extern const FileEntry file_registry[];\n")
        out.write("extern const unsigned int file_registry_count;\n")
        out.write("\n")
        out.write("/* Returns a pointer to the entry matching path (e.g. \"/index.html\"), or NULL. */\n")
        out.write("const FileEntry *file_registry_find(const char *path);\n")
        out.write("\n")
        out.write("#endif /* FILE_REGISTRY_H */\n")

    # Source
    with open(source_out, "w") as out:
        out.write("/* Auto-generated by tools/gen_file_registry.py - do not edit. */\n")
        out.write("\n")
        out.write('#include <string.h>\n')
        out.write("\n")
        out.write('#include "file_registry.h"\n')
        out.write("\n")

        entries = []
        for i, (path, full) in enumerate(files):
            with open(full, "rb") as f:
                data = f.read()
            data = apply_version_placeholder(path, data, version_info["full"], version_info["build_time"])
            stored, compressed = compress_entry(data)
            emit_c_array(out, f"file_{i}", stored)
            out.write("\n")
            entries.append((path, compressed, len(data), len(stored)))

        out.write("const FileEntry file_registry[] = {\n")
        for i, (path, _) in enumerate(files):
            content_type = detect_content_type(path)
            _, compressed, orig_size, stored_size = entries[i]
            out.write(
                f'    {{ "{path}", file_{i}, {stored_size}, {orig_size}, '
                f'{1 if compressed else 0}, "{content_type}" }},\n'
            )
        out.write("};\n")
        out.write("\n")
        out.write("const unsigned int file_registry_count =\n")
        out.write("    sizeof(file_registry) / sizeof(file_registry[0]);\n")
        out.write("\n")
        out.write("const FileEntry *file_registry_find(const char *path) {\n")
        out.write("    if (!path)\n")
        out.write("        return NULL;\n")
        out.write("\n")
        out.write("    for (unsigned int i = 0; i < file_registry_count; i++) {\n")
        out.write('        if (strcmp(file_registry[i].path, path) == 0)\n')
        out.write("            return &file_registry[i];\n")
        out.write("    }\n")
        out.write("\n")
        out.write("    return NULL;\n")
        out.write("}\n")

    print(f"Generated {header_out} and {source_out} ({len(files)} files, {manifest_path})")


if __name__ == "__main__":
    main()
