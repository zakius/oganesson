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
_platform_late=/oganesson/windows/late
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

# Runs a command in clone.py's environment, as its Google Storage downloads
# need: its depot_tools (and their vpython3, on the system Python) first.
with_depot_tools() {
    local tools="${_src_dir}/uc_staging/depot_tools"
    PATH="$tools:$PATH" PYTHONPATH="$tools" DEPOT_TOOLS_UPDATE=0 PYTHONDONTWRITEBYTECODE=1 \
        PYTHONWARNINGS=ignore::SyntaxWarning \
        VPYTHON_BYPASS='manually managed python not supported by chrome operations' "$@"
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
    # The build runs the image's Node (22, as helium-linux's builds do) rather
    # than the Node 24 Chromium checks for: helium-linux's patch dropping the check.
    ln -s /oganesson/linux/helium-linux/patches/ungoogled-chromium/portablelinux/drop-nodejs-version-check.patch \
        "$_platform_patches/drop-nodejs-version-check.patch"
    echo drop-nodejs-version-check.patch >> "$_platform_patches/series"
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

# Windows' own dependencies (DirectX and WebAuthn headers, WTL, the LZMA SDK's
# tools...): the clone's gclient config, with Windows added to its targets.
windows_deps() {
    [ -f "${_src_dir}/.windeps.stamp" ] && return
    local staging="${_src_dir}/uc_staging"
    # The copy's gclient state, and clone.py's patched gclient, name the Linux
    # tree's paths: this tree's instead, or gclient would go through the Linux tree.
    { grep -rlIZ /oganesson/work/helium-linux/build/src "$staging" || true; } |
        xargs -0 -r sed -i "s|/oganesson/work/helium-linux/build/src|${_src_dir}|g"
    sed -i "s|^target_os = .*|target_os = ['unix', 'win'];|" "$staging/.gclient"
    if grep -rqI /oganesson/work/helium-linux "$staging"; then
        echo "gclient state still names the Linux tree" >&2
        exit 1
    fi
    (cd "$staging" &&
        with_depot_tools python3 depot_tools/gclient.py sync --nohooks --no-history --shallow -j 8)
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
    # Both public on Google Storage, named by the files the tree pins them in.
    local gcs=https://storage.googleapis.com rc=build/toolchain/win/rc/linux64/rc
    curl -sfL -o "$rc" "$gcs/chromium-browser-clang/rc/$(cat "$rc.sha1")"
    echo "$(cat "$rc.sha1")  $rc" | sha1sum -c --quiet
    chmod +x "$rc"
    local profile
    profile="chrome/build/pgo_profiles/$(cat chrome/build/win64.pgo.txt)"
    mkdir -p chrome/build/pgo_profiles
    [ -f "$profile" ] || curl -sfL -o "$profile" \
        "$gcs/chromium-optimization-profiles/pgo_profiles/${profile##*/}"
    python3 build/vs_toolchain.py update --force
    cd - >/dev/null
}

# Helium's and helium-windows' arguments, and ours: an official build for
# Windows, with V8's instance types from Torque (its metagen alternative runs
# libclang in clang-cl mode, which on Linux reads its absolute input path as an
# option). Written when they change; the build then reruns gn itself.
write_windows_args() {
    mkdir -p "$_out_dir"
    { cat "${_main_repo}/flags.gn" "${_root_dir}/flags.windows.gn"
      printf '%s\n' 'target_os="win"' 'is_official_build=true' \
          'v8_use_metagen_instance_types=false'; } > "${_out_dir}/args.gn.new"
    if cmp -s "${_out_dir}/args.gn.new" "${_out_dir}/args.gn"; then
        rm "${_out_dir}/args.gn.new"
    else
        mv "${_out_dir}/args.gn.new" "${_out_dir}/args.gn"
    fi
}

# A tree prepared for other inputs (or the Linux tree it was copied from).
echo "Inputs ${OGANESSON_PATCH_HASH}; the tree's: $(cut -d' ' -f2 "$stamp" 2>/dev/null)"
if [ -f "${_src_dir}/.downloaded.stamp" ] &&
    { [ ! -f "$stamp" ] || [ "$(cut -d' ' -f2 "$stamp")" != "$OGANESSON_PATCH_HASH" ]; }; then
    reset_tree
fi

if [ ! -f "$stamp" ]; then
    windows_deps
    platform_series
    prepare_tree
    restore_win_build_output
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

write_windows_args
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
# Firefox Sync's Rust library, loaded by the browser from its folder, then the
# installer, whose payload includes it, and the packages.
bash /oganesson/windows/build-sync-lib.sh "$_src_dir" "$_out_dir"
python3 third_party/depot_tools/autoninja.py -C "$_out_dir" "${jobs[@]}" setup mini_installer
bash /oganesson/windows/package.sh "$_out_dir" /oganesson/work/dl/windows
