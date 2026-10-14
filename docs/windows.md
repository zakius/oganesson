# Windows

The Windows x64 build is cross-compiled on Linux, in a container, from the same sources as the Linux build:

```sh
./oganesson.py build --windows
```

It builds the browser, the Sync library and the packages, in `work/dl/windows/<version>-1.<commit time>/`:

- `oganesson-<version>-windows-x64-installer.exe`: helium-windows' NSIS installer around Chromium's `setup.exe`. It installs for the current user (`%LOCALAPPDATA%\oganesson`) or for all users.
- `oganesson-<version>-windows-x64.zip`: the browser's folder, to unpack anywhere.

Both are unsigned, so SmartScreen warns about them until enough people run them. There is no auto-updater: helium-windows' WinSparkle updater is left out (`windows/helium-windows-drops.txt`).

## How it builds

| Step | What |
|---|---|
| Tree | `work/helium-windows/build/src`, a copy of the Linux tree's fetched sources that shares their blocks on btrfs, plus Windows' own dependencies (gclient with `target_os` `win`). The Linux tree has to be fetched first. |
| Patches | Helium's series, helium-windows' (minus `windows/helium-windows-drops.txt`, plus helium-linux's Node version check patch), ours, `late/`, then `windows/late/`. |
| Toolchain | Chromium's Linux clang and lld. MSVC's headers and libraries and the Windows SDK come from Microsoft through [msvc-wine](https://github.com/mstorsjo/msvc-wine), whose use accepts Microsoft's license terms. `windows/make_toolchain.py` packs them the way Chromium's build expects, once per toolchain pin. |
| Sync | `windows/build-sync-lib.sh`: the Rust library as `oganesson_sync.dll`, with NSS, NSPR and SQLite from MSYS2's UCRT64 packages next to it. |
| Packages | `windows/package.sh`. |

What the cross build changes, and why:

- `windows/late/installer-host-7zip.patch`: the installer's payload is packed with the build host's 7-Zip. helium-windows looks for an installed 7-Zip in Windows' registry.
- `windows-disable-rcpy.patch` is dropped: Chromium's own resource compiler runs on Linux, Microsoft's `rc.exe` doesn't.
- `v8_use_metagen_instance_types=false`: V8's instance types come from Torque. Its metagen step runs libclang in clang-cl mode, which on Linux reads the absolute input path as an option.
- The MIDL and message compiler outputs that ungoogled-chromium's pruning removes are restored from git: Chromium ships them pre-generated for hosts without Microsoft's tools.
- The Sync library defines `VerifyCodeSigningCertificateChain`, which fails. Only Mozilla's own NSS builds have it, and nothing calls it.

## Licenses

The packages include Microsoft's runtime DLLs (`vcruntime140*.dll`, `msvcp140*.dll` and the UCRT), which Microsoft's license lets applications redistribute, and the Debugging Tools' `dbghelp.dll` and `dbgcore.dll`. NSS and NSPR are MPL-2.0, and SQLite is public domain. MSYS2 publishes the sources of the exact packages `windows/build-sync-lib.sh` pins.

## Testing in a VM

A Windows 11 VM in Docker ([dockur/windows](https://github.com/dockur/windows)) runs the installer and the browser. Its files are in `work/win/vm`: `storage/` (the disk), `share/` (`\\host.lan\Data` in Windows), `oem/install.bat` (first-logon setup: OpenSSH for `ssh_key`), and `password` for the `oganesson` user. The VM's screen is at port 8006 in a web browser, and RDP is on port 3389. SSH is on port 2222, from this machine only:

```sh
ssh -i work/win/vm/ssh_key -p 2222 oganesson@127.0.0.1
```

SSH runs outside the desktop session. `share/run-oganesson.ps1` starts the browser in it, and `share/gui-install.ps1` reinstalls with the installer's GUI.
