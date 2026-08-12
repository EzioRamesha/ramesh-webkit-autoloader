#!/usr/bin/env python3
"""Inject Iris continue-JB guard into patched slopkit poops.html.

After WebKit prep (bootChain), probe 127.0.0.1:9021. If elfldr is already
listening, skip the kernel ladder and run configured autoload (kstuff→pldmgr).
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
POOPS = ROOT / "frontend" / "autoloader" / "slopkit" / "slopkit" / "poops.html"

PROBE_FN = r"""
async function probeElfldrListening() {
    preparePayloadSender();
    let fd = -1;
    try {
        let result = await sys(SYS_SOCKET, 2, 1, 0);
        if (result.failed || result.s32 < 0) return false;
        fd = result.s32;
        track(fd);
        result = await sys(SYS_CONNECT, fd, payloadSockaddrStore.ptr, 0x10);
        const ok = !result.failed && result.s32 === 0;
        const closeRes = await sys(SYS_CLOSE, fd);
        if (!closeRes.failed && closeRes.s32 === 0) untrack(fd);
        flushMark("ELFLDR-PROBE", "up=" + (ok ? 1 : 0));
        return ok;
    } catch (e) {
        flushMark("ELFLDR-PROBE-ERR",
            clean(e && e.message ? e.message : e));
        return false;
    }
}

"""

ANCHOR = """        await bootChain();

        await chooseCore();"""

REPLACEMENT = """        await bootChain();

        /* Iris continue-JB: WebKit prep is enough for syscalls; if elfldr is
           already live, never climb the kernel ladder again this boot. */
        stage("checking whether elfldr is already on 127.0.0.1:" + PAYLOAD_PORT);
        const elfldrUp = await probeElfldrListening();
        if (elfldrUp) {
            elfldrSpawned = true;
            stage("ALREADY JAILBROKEN — elfldr live — skipping kernel ladder", "ok");
            flushMark("CONTINUE-OK", "elfldr-up=1-iris=1");
            try {
                window.parent.postMessage({
                    type: "wkal", kind: "continue", ok: true, elfldr: true
                }, "*");
            } catch (e) { }
            showPayloadMenu();
            if (typeof runConfiguredAutoload === "function")
                runConfiguredAutoload();
            return;
        }
        flushMark("CONTINUE-FRESH", "elfldr-up=0");

        await chooseCore();"""


def main() -> int:
    if not POOPS.is_file():
        print(f"Error: {POOPS} missing — run tools/apply_slopkit_patch.sh first",
              file=sys.stderr)
        return 1
    text = POOPS.read_text(encoding="utf-8")
    changed = False

    if "async function probeElfldrListening()" not in text:
        # Insert probe helper just before async function main()
        marker = "async function main() {"
        if marker not in text:
            print("Error: async function main() not found", file=sys.stderr)
            return 1
        text = text.replace(marker, PROBE_FN + marker, 1)
        changed = True
    else:
        print("continue-guard: probeElfldrListening already present")

    if "CONTINUE-OK" in text and "elfldr-up=1-iris=1" in text:
        print("continue-guard: main() skip already injected")
    elif ANCHOR not in text:
        print("Error: bootChain/chooseCore anchor not found", file=sys.stderr)
        return 1
    else:
        text = text.replace(ANCHOR, REPLACEMENT, 1)
        changed = True

    if changed:
        POOPS.write_text(text, encoding="utf-8")
        print(f"continue-guard: injected into {POOPS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
