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
| Tree | `work/helium-windows/build/src`, a Windows checkout: helium's `clone.py -p win64`, gclient with Windows' dependencies and the hooks that fetch the Linux-hosted build tools and Windows' PGO profile. |
| Patches | Helium's series, helium-windows' (minus `windows/helium-windows-drops.txt`), ours, `late/`, then `windows/late/`. |
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

`windows/vm/vm.sh` runs a Windows 11 VM in Docker ([dockur/windows](https://github.com/dockur/windows), with KVM), for the installer and the browser:

```sh
windows/vm/vm.sh start [ADDRESS]   # first time: downloads and installs Windows unattended
windows/vm/vm.sh install           # the newest installer, with its GUI, on the VM's desktop
windows/vm/vm.sh run               # the installed browser on the VM's desktop
windows/vm/vm.sh ssh               # PowerShell in the VM
```

Its screen is at http://localhost:8006, and with ADDRESS (for example this machine's Tailscale address) also there, with RDP on port 3389. The VM's files are in `work/win/vm`: the disk (`storage/`), the shared folder (`share/`, `\\host.lan\Data` in Windows), the SSH key and the `oganesson` user's password. On first logon, `windows/vm/install.bat` turns on Windows' OpenSSH server for that key. SSH runs outside the desktop session, so the scripts start the installer and the browser in it with scheduled tasks.
