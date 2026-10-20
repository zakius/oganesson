#!/usr/bin/env bash
# Runs inside the Windows builder container (windows/Dockerfile, started by
# oganesson.py build --windows): cross-compiles the Windows x64 release build
# on Linux into work/helium-windows/build/src/out/Release.
# The steps are helium-windows' build.py's, in its order, with its --clone
# sources: helium's clone.py -p win64 (gclient with Windows' dependencies and
# the hooks that fetch the build's tools, Linux-hosted here, and Windows' PGO
# profile). Its default, the prepared win-x64 archive, holds Windows-hosted
# tools. Then Helium's series, helium-windows' platform patches and ours. The
# toolchain is Chromium's own, as there: its clang, lld and Rust. MSVC's
# headers and libraries and the Windows SDK, which build.py takes from the
# installed Visual Studio, are a toolchain package made here once
# (windows/make_toolchain.py), mounted case-insensitively by Chromium's
# build/vs_toolchain.py.
set -euo pipefail

. /oganesson/linux/helium-linux/scripts/shared.sh
. /oganesson/tools/prepare.sh
setup_environment
_main_repo=/work/helium-tree
_root_dir=/oganesson/windows/helium-windows
_platform_late=/oganesson/windows/late
_build_dir=/work/helium-windows/build
_dl_cache="${_build_dir}/download_cache"
_src_dir="${_build_dir}/src"
_namesubs_cache="${_build_dir}/namesubs.tar"
_out_dir="${_src_dir}/out/Release"
_mtimes="${_src_dir}/../oganesson-mtimes.tsv"
stamp="${_src_dir}/.oganesson-prepared"
mkdir -p "$_dl_cache"

# MSVC and the Windows SDK at the versions Chromium's build/vs_toolchain.py
# pins, from Microsoft through msvc-wine (whose use accepts Microsoft's license
# terms), packed as Chromium's toolchain package. Made again when Chromium
# moves its pin (TOOLCHAIN_HASH); MSVC_VERSION is then the toolset its new
# Visual Studio has.
toolchain=/work/win/toolchain
MSVC_VERSION=14.51
msvc_wine_commit=514f8ea
windows_msvc() {
    local vs="$_src_dir/build/vs_toolchain.py" win=/work/win
    pin_hash="$(sed -n "s/^TOOLCHAIN_HASH = '\(.*\)'/\1/p" "$vs")"
    [ "$(cat "$toolchain/pin" 2>/dev/null)" = "$pin_hash" ] && return
    local sdk
    sdk="$(sed -n "s/^SDK_VERSION = '\(10\.0\.[0-9]*\)\.0'/\1/p" "$vs")"
    [ -d "$win/msvc-wine" ] || git clone -q https://github.com/mstorsjo/msvc-wine "$win/msvc-wine"
    git -C "$win/msvc-wine" checkout -q "$msvc_wine_commit"
    rm -rf "$win/msvc" "$toolchain"
    python3 "$win/msvc-wine/vsdownload.py" --accept-license --cache "$win/cache" \
        --dest "$win/msvc" --msvc-version "$MSVC_VERSION" --sdk-version "$sdk" \
        --architecture x64 x86 --host-arch x64
    mkdir -p "$toolchain"
    python3 /oganesson/windows/make_toolchain.py "$win/msvc" "$_src_dir" "$toolchain"
    echo "$pin_hash" > "$toolchain/pin"
}

# helium-windows' series without windows/helium-windows-drops.txt: a folder of
# links to its patches, with its own series.
_platform_patches="${_build_dir}/helium-windows-patches"
platform_series() {
    rm -rf "$_platform_patches"
    mkdir -p "$_platform_patches"
    local entry
    for entry in "$_root_dir"/patches/*; do
        [ "$(basename "$entry")" = series ] || ln -s "$entry" "$_platform_patches/"
    done
    grep -vxF -f <(cut -f1 /oganesson/windows/helium-windows-drops.txt | grep -v '^#') \
        "$_root_dir/patches/series" > "$_platform_patches/series"
}

# Chromium's pre-generated MIDL and message compiler outputs, which a Linux
# host can't make (Microsoft's midl.exe and mc.exe): pruning removes them as
# binaries, git has them.
restore_win_build_output() {
    local path repo
    grep win_build_output "${_main_repo}/pruning.list" | while read -r path; do
        repo="$(dirname "$path")"
        until [ -e "${_src_dir}/$repo/.git" ]; do repo="$(dirname "$repo")"; done
        git -C "${_src_dir}/$repo" checkout HEAD -- "${path#"$repo"/}"
    done
}

# helium-windows' resources, from our branding (work/helium-tree/resources):
# prepare_tree copies them before Helium's.
platform_resources() {
    local gen
    gen="$(mktemp -d)"
    sed "s|^\.\./helium-chromium/|${_main_repo}/|" "$_root_dir/resources/generate_resources.txt" \
        > "$gen/generate_resources.txt"
    mkdir -p "$gen/generated"
    python3 "$_main_repo/utils/generate_resources.py" "$gen/generate_resources.txt" "$gen"
    python3 "$_main_repo/utils/replace_resources.py" "$_root_dir/resources/platform_resources.txt" \
        "$gen" "$_src_dir"
    rm -rf "$gen"
}

# The updater's public key, windows/update-key.pem, as WinSparkle takes it: the
# raw 32 bytes in base64, the end of the key's DER form.
update_key() {
    openssl pkey -pubin -in /oganesson/windows/update-key.pem -outform DER | tail -c 32 | base64
}

# build.py's arguments: Helium's, helium-windows', is_official_build and, as
# build.py writes them when the updater has its key, the updater's. Ours
# (flags.gn) after them. And the
# cross build's: target_os, and V8's instance types from Torque (its metagen
# alternative runs libclang in clang-cl mode, which on Linux reads its absolute
# input path as an option). Written when they change; the build then reruns gn
# itself.
write_windows_args() {
    mkdir -p "$_out_dir"
    { cat "${_main_repo}/flags.gn"; echo; cat "${_root_dir}/flags.windows.gn"
      printf '%s\n' 'target_os="win"' 'v8_use_metagen_instance_types=false' \
          'is_official_build=true' 'mojom_message_id_salt_path="//chrome/MOJOM_SALT"' \
          'enable_winsparkle=true' "winsparkle_ed_key=\"$(update_key)\""
      cat /oganesson/flags.gn; } > "${_out_dir}/args.gn.new"
    if cmp -s "${_out_dir}/args.gn.new" "${_out_dir}/args.gn"; then
        rm "${_out_dir}/args.gn.new"
    else
        mv "${_out_dir}/args.gn.new" "${_out_dir}/args.gn"
    fi
}

# gclient's toolchain hook would fetch Google's own package: ours comes after.
DEPOT_TOOLS_WIN_TOOLCHAIN=0 fetch_pinned win64
windows_msvc
export DEPOT_TOOLS_WIN_TOOLCHAIN=1 DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL="$toolchain"
export "GYP_MSVS_HASH_${pin_hash}=$(cat "$toolchain/hash")"
write_windows_args
if [ ! -f "$stamp" ]; then
    platform_series
    # WinSparkle's source, which helium-windows' updater patches change and
    # build in: build.py fetches it with the rest of downloads.ini.
    rm -rf "${_src_dir}/third_party/winsparkle"
    "${_main_repo}/utils/downloads.py" retrieve -i "$_root_dir/downloads.ini" -c "$_dl_cache" \
        --components winsparkle
    "${_main_repo}/utils/downloads.py" unpack -i "$_root_dir/downloads.ini" -c "$_dl_cache" \
        "$_src_dir" --components winsparkle
    prepare_tree
    restore_win_build_output
    mark_prepared
fi

# vs_toolchain mounts the toolchain package with ciopfs (unpacking it the first
# time); the mount ends with the container.
(cd "$_src_dir" && python3 build/vs_toolchain.py update --force)
if [ ! -f "${_out_dir}/build.ninja" ]; then
    (cd "$_src_dir" && ./buildtools/linux64/gn gen "$_out_dir" --fail-on-unused-args)
fi
cd "$_src_dir"
jobs=()
[ -n "${OGANESSON_JOBS:-}" ] && jobs=(-j "$OGANESSON_JOBS")
export SISO_PATH="${_src_dir}/third_party/siso/cipd/siso"
build_ours
# The version folder's assembly manifest, <version>.manifest, stays in the out
# folder after the next version's build, and the zip (FILES.cfg) and the
# installer (chrome.release) take every *.manifest there.
version="$(cat /oganesson/helium/chromium_version.txt)"
find "$_out_dir" -maxdepth 1 -name '*.manifest' ! -name "$version.manifest" -delete
# Firefox Sync's Rust library, loaded by the browser from its folder: before
# build.py's targets, as the installer's payload includes it.
bash /oganesson/windows/build-sync-lib.sh "$_src_dir" "$_out_dir"
python3 third_party/depot_tools/autoninja.py -C "$_out_dir" "${jobs[@]}" \
    chrome chromedriver setup mini_installer
bash /oganesson/windows/package.sh "$_out_dir" /work/dl/windows
