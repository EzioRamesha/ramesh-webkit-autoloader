<p align="center">
 <img src="./assets/icon.svg" width="128" />
</p>
<h1 align="center">Ramesh WebKit Autoloader</h1>
&nbsp;
<p align="center">
  Offline homescreen WebKit jailbreak for PS5 (FW <b>9.00–12.00</b>).<br>
  Developed by <b>Ramesh</b> · <a href="https://github.com/EzioRamesha">EzioRamesha</a>
</p>

> [!NOTE]
> Fork of [itsPLK/ps5-webkit-autoloader](https://github.com/itsPLK/ps5-webkit-autoloader) (GPL-3.0).
> Uses [jordyidk/slopkit](https://github.com/jordyidk/slopkit) under the hood.
> After JB this fork auto-injects **kstuff-lite → pldmgr**, always preferring
> GitHub **latest** releases, with local AppCache mirrors as offline fallback.

## What this is

| Step | What happens |
|------|----------------|
| One-time install | Installer ELF (or PC host + DNS) creates a homescreen app and caches the exploit page on the PS5 |
| Daily use | Launch **WebKit Autoloader** from the homescreen — **no internet / no PC DNS required** |
| After JB | Auto: **EchoStretch kstuff-lite** (latest) → **itsPLK Payload Manager** (latest); if kstuff fails, pldmgr still runs |

Same idea as PLK’s offline autoloader; payload chain matches [slopkit-lite](https://github.com/EzioRamesha/slopkit-lite).

## Setup

### Already jailbroken

1. Build or download `webkit-autoloader-installer_*.elf` from [Releases](https://github.com/EzioRamesha/ramesh-webkit-autoloader/releases).
2. Send it with `elfldr` / Payload Manager.
3. Installer creates the homescreen app, opens the browser once to **AppCache** the page, exits.
4. **Reboot once**, then launch **WebKit Autoloader** from the homescreen.

### Not jailbroken yet

1. Run `webkit-autoloader-host` (Python / Windows exe) on a PC on your LAN.
2. Set PS5 DNS to that PC’s IP.
3. Open **User’s Guide** — host serves the installer path.
4. **Reboot once**, then use the homescreen app offline.

## Build (developers)

```bash
git submodule update --init --recursive
# Requires Dockerized ps5-payload-sdk (see upstream Dockerfile.sdk)
./build_release.sh
```

`scripts/download_deps.sh` always refreshes:

- `frontend/autoloader/payloads/kstuff-lite.elf` ← EchoStretch/kstuff-lite **latest**
- `frontend/autoloader/payloads/pldmgr.elf` ← itsPLK/ps5-payload-manager **latest**

Runtime also tries those GitHub URLs first; offline falls back to the cached mirrors.

## Credits

* **Ramesh (EzioRamesha)** — this fork: branding, kstuff-lite→pldmgr always-latest chain, lite host alignment
* **[itsPLK](https://github.com/itsPLK)** — [ps5-webkit-autoloader](https://github.com/itsPLK/ps5-webkit-autoloader), Payload Manager, unified autoloader
* **[jordyidk](https://github.com/jordyidk)** & contributors — [slopkit](https://github.com/jordyidk/slopkit)
* **EchoStretch** — [kstuff-lite](https://github.com/EchoStretch/kstuff-lite)
* **john-tornblom** — ps5-payload-sdk
* Original research: Egy, Sonic, Yenyen, Zeco, Gezine, EchoStretch, Ufm42, TheFloW, John Tornblom, Flatz, PS5 R&D Discord

## License

GPL-3.0 (same as upstream). Keep this license and upstream credits when redistributing.

## Disclaimer

Research / development use only. Use at your own risk.
