#!/usr/bin/env bash
# Packs the Windows build (OUT, after windows/container-build.sh built chrome,
# the Sync library, setup and mini_installer) for download, into
# DEST/<version>-1.<commit time>/:
#   oganesson-<version>-windows-x64.zip            the browser's folder, to unpack
#                                                   anywhere (Chromium's FILES.cfg)
#   oganesson-<version>-windows-x64-installer.exe  helium-windows' NSIS installer
#                                                   around Chromium's setup.exe
#   oganesson-<version>-windows-x64-update.exe     Chromium's mini_installer, which
#                                                   the browser's updater runs
# No Authenticode signature: Windows SmartScreen warns about the first two until
# enough people run them. windows/publish.sh signs the update for the updater.
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

# The zip: what FILES.cfg lists for official builds, without the installer's files, in a
# folder, each entry with the commit's time. Every file is deflated with Zopfli (pigz -11),
# in parallel, and chrome.dll with every CPU, as pigz splits it into blocks: smaller than
# 7-Zip's best deflate, and minutes faster.
nsi="$(mktemp --suffix=.nsi)"
trap 'rm -f "$nsi"' EXIT
rm -f "$dir/$name.zip"
python3 - "$src" "$out" "$dir/$name.zip" "$name" <<'EOF'
import os, subprocess, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, '/oganesson/helium/utils')
import filescfg
src, out, zip_path, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
excluded = {Path(n) for n in ('mini_installer.exe', 'mini_installer_exe_version.rc',
                              'setup.exe', 'oganesson.packed.7z')}
date_time = time.gmtime(int((src / 'build/util/LASTCHANGE.committime').read_text()))[:6]
files = []
for relative in filescfg.filescfg_generator(src / 'chrome/tools/build/win/FILES.cfg', out,
                                            '64bit', excluded):
    path = out / relative
    files += sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]


def deflate(path):
    """The file's content and its raw deflate stream, out of pigz's zlib header and Adler-32."""
    data = path.read_bytes()
    threads = os.cpu_count() if len(data) > 8 << 20 else 1
    return data, subprocess.run(['pigz', '-11', '-z', '-p', str(threads), '-c'], input=data,
                                capture_output=True, check=True).stdout[2:-4]


class Precompressed:
    """A compressor for zipfile that returns a stream deflated beforehand."""

    def __init__(self, stream):
        self.stream = stream

    def compress(self, data):
        return b''

    def flush(self):
        return self.stream


stock = zipfile._get_compressor
with ThreadPoolExecutor(os.cpu_count()) as pool, zipfile.ZipFile(zip_path, 'w') as archive:
    folders = set()
    for path, (data, stream) in zip(files, pool.map(deflate, files)):
        entry = Path(name, path.relative_to(out))
        for folder in reversed(entry.parents[:-1]):
            if folder not in folders:
                folders.add(folder)
                info = zipfile.ZipInfo(f'{folder}/', date_time)
                info.external_attr = 0o40755 << 16 | 0x10  # a folder, for Windows too
                archive.writestr(info, b'')
        info = zipfile.ZipInfo(str(entry), date_time)
        info.external_attr = 0o100644 << 16 | 0x20  # Windows' archive bit, as 7-Zip sets it
        # Tiny files that deflate doesn't shrink are stored.
        if len(stream) < len(data):
            info.compress_type = zipfile.ZIP_DEFLATED
            zipfile._get_compressor = lambda kind, level=None: Precompressed(stream)
        archive.writestr(info, data)
        zipfile._get_compressor = stock
EOF

# The installer: helium-windows' script with our names (the install folder as
# windows/late/branding.patch has it: no company folder).
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

# The update: the browser's updater runs it with --do-not-launch-chrome.
cp "$out/mini_installer.exe" "$dir/$name-update.exe"
ls -l "$dir"
