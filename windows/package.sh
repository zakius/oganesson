#!/usr/bin/env bash
# Packs the Windows build (OUT, after windows/container-build.sh built chrome,
# the Sync library, setup and mini_installer) for download, into
# DEST/<version>-1.<commit time>/:
#   oganesson-<version>-windows-x64.zip            the browser's folder, to unpack
#                                                   anywhere (Chromium's FILES.cfg)
#   oganesson-<version>-windows-x64-installer.exe  helium-windows' NSIS installer
#                                                   around Chromium's setup.exe
# Unsigned: Windows SmartScreen warns about both until enough people run them.
# Runs inside the Windows build container. Usage: windows/package.sh OUT DEST
set -euo pipefail
out="$(realpath "$1")"
dest="$2"
src="$(realpath "$out/../..")"
helium_windows=/oganesson/windows/helium-windows
# Chromium's version, as patches/helium-utils.patch makes the build's.
version="$(cat /oganesson/helium/chromium_version.txt)"
# The commit time, from oganesson.py: a worktree's git folder isn't in the container.
release="1.${OGANESSON_COMMIT_TIME:?}"
dir="$dest/$version-$release"
mkdir -p "$dir"
name="oganesson-$version-windows-x64"

# The zip: what FILES.cfg lists for official builds, without the installer's files.
python3 - "$src" "$out" "$dir/$name.zip" <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, '/oganesson/helium/utils')
import filescfg
src, out, zip_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
excluded = {Path(n) for n in ('mini_installer.exe', 'mini_installer_exe_version.rc',
                              'setup.exe', 'oganesson.packed.7z')}
files = filescfg.filescfg_generator(src / 'chrome/tools/build/win/FILES.cfg', out, '64bit',
                                    excluded)
timestamp = int((src / 'build/util/LASTCHANGE.committime').read_text())
filescfg.create_archive(files, (), out, zip_path, timestamp)
EOF

# The installer: helium-windows' script with our names (the install folder as
# windows/late/branding.patch has it: no company folder).
nsi="$(mktemp --suffix=.nsi)"
trap 'rm -f "$nsi"' EXIT
sed -e 's/^!define PRODUCT_NAME "Helium"/!define PRODUCT_NAME "oganesson"/' \
    -e 's/^!define PRODUCT_PUBLISHER "imput"/!define PRODUCT_PUBLISHER "oganesson"/' \
    -e 's/^!define PRODUCT_COMPANY_PATH "imput"/!define PRODUCT_COMPANY_PATH ""/' \
    -e 's/^!define PRODUCT_GUID ".*"/!define PRODUCT_GUID "{161B2895-4044-4BBE-B56B-942B997EB7D0}"/' \
    -e 's/Copyright The Helium Authors/Copyright The oganesson Authors/' \
    -e 's/helium_install/oganesson_install/g; s/helium\.7z/oganesson.7z/g' \
    "$helium_windows/installer/helium.nsi" > "$nsi"
if grep -n 'imput\|"Helium\|helium_install' "$nsi"; then
    echo "package.sh: helium.nsi has Helium names this doesn't rename" >&2
    exit 1
fi
makensis -V2 -NOCD -DVERSION="$version" -DARCH=x64 -DSETUP_EXE="$out/setup.exe" \
    -DHELIUM_7Z="$out/oganesson.packed.7z" \
    -DICON_FILE="$src/chrome/app/theme/chromium/win/chromium.ico" \
    -DOUTPUT_FILE="$dir/$name-installer.exe" -DLICENSE_FILE=/oganesson/LICENSE "$nsi"
ls -l "$dir"
