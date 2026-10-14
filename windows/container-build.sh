#!/usr/bin/env bash
# Runs inside the Windows builder container (windows/Dockerfile, started by
# oganesson.py build --windows): cross-compiles the Windows x64 release build
# on Linux into work/helium-windows/build/src/out/Release.
# The tree starts as a copy of the Linux tree's fetched sources (helium's
# clone.py fetches the same sources for every platform), gets Windows' own
# dependencies once, then Helium's series, helium-windows' platform patches
# and ours. The compiler is Chromium's Linux clang; MSVC's headers and
# libraries and the Windows SDK come from work/win/toolchain
# (windows/make_toolchain.py), mounted case-insensitively by Chromium's
# build/vs_toolchain.py.
set -euo pipefail

. /oganesson/linux/helium-linux/scripts/shared.sh
. /oganesson/tools/prepare.sh
setup_environment
_main_repo=/oganesson/work/helium-tree
_root_dir=/oganesson/windows/helium-windows
_build_dir=/oganesson/work/helium-windows/build
_dl_cache="${_build_dir}/download_cache"
_src_dir="${_build_dir}/src"
_namesubs_cache="${_build_dir}/namesubs.tar"
_out_dir="${_src_dir}/out/Release"
_mtimes="${_src_dir}/../oganesson-mtimes.tsv"
stamp="${_src_dir}/.oganesson-prepared"
mkdir -p "$_dl_cache"

# The toolchain package: Chromium's pin, mapped to ours.
toolchain=/oganesson/work/win/toolchain
pin_hash="$(sed -n "s/^TOOLCHAIN_HASH = '\(.*\)'/\1/p" "$_src_dir/build/vs_toolchain.py")"
export DEPOT_TOOLS_WIN_TOOLCHAIN=1
export DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL="$toolchain"
export "GYP_MSVS_HASH_${pin_hash}=$(cat "$toolchain/hash")"

# Windows' own dependencies (DirectX and WebAuthn headers, WTL, the LZMA SDK's
# tools...): the clone's gclient config, with Windows added to its targets.
windows_deps() {
    [ -f "${_src_dir}/.windeps.stamp" ] && return
    local staging="${_src_dir}/uc_staging"
    sed -e "s|/oganesson/work/helium-linux/build/src|${_src_dir}|g" \
        -e "s|^target_os = .*|target_os = ['unix', 'win'];|" \
        "$staging/.gclient" > "$staging/.gclient-win"
    (cd "$staging" && GCLIENT_FILE="$staging/.gclient-win" DEPOT_TOOLS_UPDATE=0 \
        python3 depot_tools/gclient.py sync --nohooks --no-history --shallow -j 8)
    touch "${_src_dir}/.windeps.stamp"
}

# Helium's Windows icons, from our branding (work/helium-tree/resources).
windows_resources() {
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

# What a Windows checkout's DEPS hooks add on a Linux host: clang's Windows
# runtime libraries, the resource compiler, the PGO profile, then the
# toolchain package (vs_toolchain mounts it with ciopfs and unpacks it).
windows_toolchain() {
    cd "$_src_dir"
    python3 -c "import sys; sys.path.insert(0, 'tools/clang/scripts'); import update; \
update.DownloadAndUnpackClangWinRuntime(update.LLVM_BUILD_DIR)"
    python3 third_party/depot_tools/download_from_google_storage.py --no_resume \
        --no_auth --bucket chromium-browser-clang/rc -s build/toolchain/win/rc/linux64/rc.sha1
    python3 tools/update_pgo_profiles.py --target=win64 update \
        --gs-url-base=chromium-optimization-profiles/pgo_profiles
    python3 build/vs_toolchain.py update --force
    cd - >/dev/null
}

write_windows_args() {
    [ -f "${_out_dir}/args.gn" ] && return
    mkdir -p "$_out_dir"
    cat "${_main_repo}/flags.gn" "${_root_dir}/flags.windows.gn" > "${_out_dir}/args.gn"
    printf '%s\n' 'target_os="win"' 'is_official_build=true' >> "${_out_dir}/args.gn"
}

# A tree prepared for other inputs (or the Linux tree it was copied from).
if [ -f "${_src_dir}/.downloaded.stamp" ] &&
    { [ ! -f "$stamp" ] || [ "$(cut -d' ' -f2 "$stamp")" != "$OGANESSON_PATCH_HASH" ]; }; then
    reset_tree
fi

if [ ! -f "$stamp" ]; then
    windows_deps
    prepare_tree
    windows_resources
    # helium-linux's host tools (Linux clang and Rust, node, CIPD packages),
    # which read the arguments, then Windows' own.
    write_windows_args
    setup_toolchain
    windows_toolchain
    echo "tree ${OGANESSON_PATCH_HASH}" > "$stamp"
    if [ -f "$_mtimes" ]; then
        python3 /oganesson/tools/keep_mtimes.py restore "$_src_dir" "$_mtimes"
        rm -f "$_mtimes"
    fi
fi

# vs_toolchain's ciopfs mount ends with the container: mounted again for each build.
(cd "$_src_dir" && python3 build/vs_toolchain.py update --force)
if [ ! -f "${_out_dir}/build.ninja" ]; then
    (cd "$_src_dir" && ./buildtools/linux64/gn gen "$_out_dir" --fail-on-unused-args)
fi
cd "$_src_dir"
jobs=()
[ -n "${OGANESSON_JOBS:-}" ] && jobs=(-j "$OGANESSON_JOBS")
export SISO_PATH="${_src_dir}/third_party/siso/cipd/siso"
build_ours
python3 third_party/depot_tools/autoninja.py -C "$_out_dir" "${jobs[@]}" -k 0 chrome
