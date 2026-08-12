#!/usr/bin/env python3
"""Inject Ramesh auto-chain into the patched slopkit poops.html copy.

After the PLK autoload patch, replace the single payload.elf inject with:
  1) kstuff-lite (GitHub latest, then local mirror)
  2) pldmgr      (GitHub latest via API, then local mirror)

Offline AppCache still works via the local mirrors under ../../payloads/.

Exposes runConfiguredAutoload() so Iris continue-JB can invoke payloads
without re-running the kernel ladder.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
POOPS = ROOT / "frontend" / "autoloader" / "slopkit" / "slopkit" / "poops.html"

OLD = """        if (cfg.autoload) {
            stage("autoloading " + cfg.autoload + " in 4 s", "ok");
            setTimeout(function () {
                sendPayloadToElfldr(cfg.autoload, "../../payloads/").then(function (r) {
                    flushMark("AUTOLOAD-OK", "name=" + cfg.autoload + "-bytes=" + r.bytes);
                    stage("autoloaded " + cfg.autoload + " (" + r.bytes + " bytes)", "ok");
                    try { window.parent.postMessage({ type: "wkal", kind: "autoload", ok: true, bytes: r.bytes }, "*"); } catch (e) { }
                }).catch(function (err) {
                    flushMark("AUTOLOAD-FAILED", "why=" + clean(err && err.message ? err.message : err));
                    stage("autoload failed: " + (err && err.message ? err.message : err), "bad");
                    try { window.parent.postMessage({ type: "wkal", kind: "autoload", ok: false, why: String(err && err.message || err) }, "*"); } catch (e) { }
                });
            }, 4000);
        }"""

CALL_SITE = """        runConfiguredAutoload();"""

FUNCTION_DEF = """
function runConfiguredAutoload() {
        if (cfg.autoload === "chain" || cfg.autoload === "ramesh") {
            stage("Ramesh chain: kstuff-lite then pldmgr in 4 s", "ok");
            setTimeout(function () {
                (async function () {
                    var sleep = function (ms) {
                        return new Promise(function (r) { setTimeout(r, ms); });
                    };
                    async function loadBytes(localName, remoteUrl, releaseApi, assetRe) {
                        var sources = [];
                        if (releaseApi) {
                            try {
                                var meta = await fetch(releaseApi, {
                                    cache: "no-cache",
                                    headers: { Accept: "application/vnd.github+json" }
                                });
                                if (meta.ok) {
                                    var data = await meta.json();
                                    var assets = (data && data.assets) || [];
                                    var re = assetRe || /\\.elf$/i;
                                    for (var i = 0; i < assets.length; ++i) {
                                        if (re.test(assets[i].name) && assets[i].browser_download_url) {
                                            sources.push({ kind: "remote", url: assets[i].browser_download_url });
                                            flushMark("ELF-RELEASE-RESOLVE", "tag=" + clean(data.tag_name || "")
                                                + "-asset=" + clean(assets[i].name));
                                            break;
                                        }
                                    }
                                }
                            } catch (e) {
                                flushMark("ELF-RELEASE-MISS", "name=" + clean(localName)
                                    + "-why=" + clean(e && e.message ? e.message : e));
                            }
                        }
                        if (remoteUrl)
                            sources.push({ kind: "remote", url: remoteUrl });
                        sources.push({ kind: "local", url: "../../payloads/" + encodeURIComponent(localName) });
                        var last = null;
                        for (var s = 0; s < sources.length; ++s) {
                            try {
                                var resp = await fetch(sources[s].url, {
                                    cache: "no-cache",
                                    redirect: "follow",
                                    mode: "cors"
                                });
                                if (!resp.ok) throw new Error("HTTP " + resp.status);
                                var bytes = new Uint8Array(await resp.arrayBuffer());
                                if (bytes.length < 4 || bytes[0] !== 0x7f || bytes[1] !== 0x45
                                    || bytes[2] !== 0x4c || bytes[3] !== 0x46)
                                    throw new Error("not an ELF");
                                flushMark("ELF-FETCH-OK", "name=" + clean(localName)
                                    + "-kind=" + sources[s].kind + "-bytes=" + bytes.length);
                                return bytes;
                            } catch (err) {
                                last = err;
                                flushMark("ELF-FETCH-MISS", "name=" + clean(localName)
                                    + "-kind=" + sources[s].kind
                                    + "-why=" + clean(err && err.message ? err.message : err));
                            }
                        }
                        throw last || new Error("fetch failed for " + localName);
                    }
                    async function sendNamed(localName, bytes) {
                        window.__rameshElfOverride = { name: localName, bytes: bytes };
                        try {
                            return await sendPayloadToElfldr(localName, "../../payloads/");
                        } finally {
                            window.__rameshElfOverride = null;
                        }
                    }
                    var kOk = false, pOk = false, total = 0;
                    try {
                        stage("INJECTING KSTUFF-LITE (latest, local fallback)", "");
                        var kBytes = await loadBytes(
                            "kstuff-lite.elf",
                            "https://github.com/EchoStretch/kstuff-lite/releases/latest/download/kstuff.elf",
                            "",
                            null);
                        var kRes = await sendNamed("kstuff-lite.elf", kBytes);
                        kOk = true;
                        total += kRes.bytes;
                        flushMark("KSTUFF-AUTO-OK", "bytes=" + kRes.bytes);
                        stage("KSTUFF-LITE OK — waiting before PLDMGR", "ok");
                        await sleep(2000);
                    } catch (kErr) {
                        flushMark("KSTUFF-AUTO-FAIL", "why=" + clean(kErr && kErr.message ? kErr.message : kErr));
                        stage("KSTUFF-LITE failed — still injecting PLDMGR", "bad");
                        await sleep(400);
                    }
                    try {
                        stage("INJECTING PLDMGR (latest, local fallback)", "");
                        var pBytes = await loadBytes(
                            "pldmgr.elf",
                            "",
                            "https://api.github.com/repos/itsPLK/ps5-payload-manager/releases/latest",
                            /^pldmgr.*\\.elf$/i);
                        var pRes = await sendNamed("pldmgr.elf", pBytes);
                        pOk = true;
                        total += pRes.bytes;
                        flushMark("PLDMGR-AUTO-OK", "bytes=" + pRes.bytes);
                    } catch (pErr) {
                        flushMark("PLDMGR-AUTO-FAIL", "why=" + clean(pErr && pErr.message ? pErr.message : pErr));
                        stage("PLDMGR failed: " + (pErr && pErr.message ? pErr.message : pErr), "bad");
                        try {
                            window.parent.postMessage({
                                type: "wkal", kind: "autoload", ok: false,
                                why: String(pErr && pErr.message || pErr)
                            }, "*");
                        } catch (e) { }
                        return;
                    }
                    stage((kOk ? "KSTUFF-LITE + " : "") + "PLDMGR ONLINE", "ok");
                    try {
                        window.parent.postMessage({
                            type: "wkal", kind: "autoload", ok: true,
                            bytes: total, kstuff: kOk ? 1 : 0, pldmgr: pOk ? 1 : 0
                        }, "*");
                    } catch (e) { }
                })().catch(function (err) {
                    flushMark("AUTOLOAD-FAILED", "why=" + clean(err && err.message ? err.message : err));
                    stage("autoload failed: " + (err && err.message ? err.message : err), "bad");
                    try {
                        window.parent.postMessage({
                            type: "wkal", kind: "autoload", ok: false,
                            why: String(err && err.message || err)
                        }, "*");
                    } catch (e) { }
                });
            }, 4000);
        } else if (cfg.autoload) {
            stage("autoloading " + cfg.autoload + " in 4 s", "ok");
            setTimeout(function () {
                sendPayloadToElfldr(cfg.autoload, "../../payloads/").then(function (r) {
                    flushMark("AUTOLOAD-OK", "name=" + cfg.autoload + "-bytes=" + r.bytes);
                    stage("autoloaded " + cfg.autoload + " (" + r.bytes + " bytes)", "ok");
                    try { window.parent.postMessage({ type: "wkal", kind: "autoload", ok: true, bytes: r.bytes }, "*"); } catch (e) { }
                }).catch(function (err) {
                    flushMark("AUTOLOAD-FAILED", "why=" + clean(err && err.message ? err.message : err));
                    stage("autoload failed: " + (err && err.message ? err.message : err), "bad");
                    try { window.parent.postMessage({ type: "wkal", kind: "autoload", ok: false, why: String(err && err.message || err) }, "*"); } catch (e) { }
                });
            }, 4000);
        }
}
"""

# Override fetch inside sendPayloadToElfldr when __rameshElfOverride is set.
FETCH_HOOK_OLD = """    const response = await fetch((base || "../payloads/") + encodeURIComponent(name),
        { cache: "no-store" });
    if (!response.ok)
        throw new Error("payload fetch failed: HTTP " + response.status);
    const bytes = new Uint8Array(await response.arrayBuffer());"""

FETCH_HOOK_NEW = """    let bytes;
    if (window.__rameshElfOverride && window.__rameshElfOverride.name === name
        && window.__rameshElfOverride.bytes) {
        bytes = window.__rameshElfOverride.bytes;
        flushMark("ELF-OVERRIDE", "name=" + clean(name) + "-bytes=" + bytes.length);
    } else {
        const response = await fetch((base || "../payloads/") + encodeURIComponent(name),
            { cache: "no-store" });
        if (!response.ok)
            throw new Error("payload fetch failed: HTTP " + response.status);
        bytes = new Uint8Array(await response.arrayBuffer());
    }"""

TILES_OLD = """    <a class="payloadTile" href="#" data-name="payload.elf" data-key="autoload" style="display:none"><img data-src="../ui/payload-shell-default.png" alt=""></a>"""

TILES_NEW = """    <a class="payloadTile" href="#" data-name="payload.elf" data-key="autoload" style="display:none"><img data-src="../ui/payload-shell-default.png" alt=""></a>
    <a class="payloadTile" href="#" data-name="kstuff-lite.elf" data-key="kstuff-lite" style="display:none"><img data-src="../ui/payload-kstuff-default.png" alt=""></a>
    <a class="payloadTile" href="#" data-name="pldmgr.elf" data-key="pldmgr" style="display:none"><img data-src="../ui/payload-plk-default.png" alt=""></a>"""


def main() -> int:
    if not POOPS.is_file():
        print(f"Error: {POOPS} missing — run tools/apply_slopkit_patch.sh first", file=sys.stderr)
        return 1
    text = POOPS.read_text(encoding="utf-8")
    changed = False

    if "function runConfiguredAutoload()" in text:
        print("ramesh-chain: runConfiguredAutoload already present")
    elif OLD in text:
        text = text.replace(OLD, CALL_SITE, 1)
        marker = "async function main() {"
        if marker not in text:
            print("Error: async function main() not found", file=sys.stderr)
            return 1
        text = text.replace(marker, FUNCTION_DEF + "\n" + marker, 1)
        changed = True
    elif "Ramesh chain: kstuff-lite then pldmgr" in text:
        print("ramesh-chain: already injected (legacy inline form)")
    else:
        print("Error: expected PLK autoload block not found in poops.html", file=sys.stderr)
        return 1

    if FETCH_HOOK_OLD in text:
        text = text.replace(FETCH_HOOK_OLD, FETCH_HOOK_NEW, 1)
        changed = True
    elif "window.__rameshElfOverride" in text:
        pass
    else:
        print("Error: sendPayloadToElfldr fetch block not found", file=sys.stderr)
        return 1

    if TILES_OLD in text and 'data-name="kstuff-lite.elf"' not in text:
        text = text.replace(TILES_OLD, TILES_NEW, 1)
        changed = True

    listed_old = """function payloadIsListed(name) {
    if (!/^[A-Za-z0-9._-]+\\.elf$/.test(name)) return false;
    const tiles = payloadMenuEl.getElementsByTagName("a");
    for (let i = 0; i < tiles.length; ++i)
        if (tiles[i].getAttribute("data-name") === name) return true;
    return false;
}"""
    listed_new = """function payloadIsListed(name) {
    if (!/^[A-Za-z0-9._-]+\\.elf$/.test(name)) return false;
    /* Iris chain payloads — always allowed (hidden tiles may be absent). */
    if (name === "kstuff-lite.elf" || name === "pldmgr.elf" || name === "payload.elf"
        || name === "kstuff.elf" || name === "PLK.elf")
        return true;
    const tiles = payloadMenuEl.getElementsByTagName("a");
    for (let i = 0; i < tiles.length; ++i)
        if (tiles[i].getAttribute("data-name") === name) return true;
    return false;
}"""
    if "Iris chain payloads" not in text and listed_old in text:
        text = text.replace(listed_old, listed_new, 1)
        changed = True

    if changed:
        POOPS.write_text(text, encoding="utf-8")
        print(f"ramesh-chain: injected into {POOPS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
