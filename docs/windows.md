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

`windows/container-build.sh` follows helium-windows' `build.py`: the same steps, in the same order, with the same GN arguments and Chromium's own toolchain.

| Step | What |
|---|---|
| Tree | `work/helium-windows/build/src`, from helium's `clone.py -p win64`, as `build.py --clone`: gclient with Windows' dependencies and the hooks that fetch the build's tools, Linux-hosted here, and Windows' PGO profile. Then Helium's `deps.ini`, and the pruning. |
| Patches | Helium's series, helium-windows' (minus `windows/helium-windows-drops.txt`), mine, `late/`, then `windows/late/`. Then domain and name substitution, translations, the version, helium-windows' resources and Helium's. |
| Toolchain | Chromium's Linux clang, lld and Rust. MSVC's headers and libraries and the Windows SDK come from Microsoft through [msvc-wine](https://github.com/mstorsjo/msvc-wine), whose use accepts Microsoft's license terms. `windows/make_toolchain.py` packs them the way Chromium's build expects, once per toolchain pin. |
| Arguments | Helium's `flags.gn`, helium-windows' `flags.windows.gn` and `is_official_build=true`, as `build.py` writes them, and the two below. |
| Build | Mine first (`dubna/tools/ours.py`), then `build.py`'s targets: `chrome chromedriver setup mini_installer`. |
| Sync | `windows/build-sync-lib.sh`, before `build.py`'s targets, as the installer carries it: the Rust library as `oganesson_sync.dll`, with NSS, NSPR and SQLite from MSYS2's UCRT64 packages next to it. |
| Packages | `windows/package.sh`. |

Where the cross build differs from `build.py`, and why:

- Sources: `build.py` defaults to the prepared `win-x64` archive from imput's chromium-tarballs. Its tools run on Windows only, so this uses `build.py --clone`'s path.
- `downloads.ini` isn't fetched. It has NSIS, WinSparkle and Git for Windows (for its `patch.exe`): the image has NSIS and `patch`, and the updater is left out.
- MSVC and the SDK: `build.py` takes them from the installed Visual Studio (`DEPOT_TOOLS_WIN_TOOLCHAIN=0`). Here they are a toolchain package at Chromium's pin (`DEPOT_TOOLS_WIN_TOOLCHAIN=1`).
- `target_os="win"`, which a Windows host doesn't need.
- `v8_use_metagen_instance_types=false`: V8's instance types come from Torque. Its metagen step runs libclang in clang-cl mode, which on Linux reads the absolute input path as an option.
- The MIDL and message compiler outputs that ungoogled-chromium's pruning removes are restored from git: on Windows, `midl.exe` and `mc.exe` make them again.
- `windows/late/installer-host-7zip.patch`: the installer's payload is packed with the build host's 7-Zip. helium-windows looks for an installed 7-Zip in Windows' registry.
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
