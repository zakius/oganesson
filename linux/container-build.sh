#!/usr/bin/env bash
# Runs inside the builder container (started by oganesson.py build).
# Prepares the Chromium tree once per patch set, then builds incrementally.
# Each build configuration has its own output folder in the same tree:
# out/Default for dev builds, out/Release for release builds. Release builds
# target x86-64-v2 (benchmarks showed no gain from v3, v4 or znver4); dev
# builds set no target.
# Uses helium-linux's scripts/shared.sh steps (the linux/helium-linux
# submodule), with work/helium-tree (oganesson.py's helium_tree()) as Helium's
# tree.
set -euo pipefail

mode="$1"            # dev or release

. /oganesson/linux/helium-linux/scripts/shared.sh
setup_environment
_main_repo=/oganesson/work/helium-tree
_root_dir=/oganesson/linux/helium-linux
# The tree stays where the shared base tree has it (see oganesson.py
# snapshot): Siso's cache records absolute paths.
_build_dir=/oganesson/work/helium-linux/build
_dl_cache="${_build_dir}/download_cache"
_src_dir="${_build_dir}/src"
_namesubs_cache="${_build_dir}/namesubs.tar"
mkdir -p "$_dl_cache"
if [ "$mode" = dev ]; then
    _out_dir="${_src_dir}/out/Default"
else
    _out_dir="${_src_dir}/out/Release"
fi

stamp="${_src_dir}/.oganesson-prepared"
# The unchanged files' times across a re-prepare, see tools/keep_mtimes.py.
_mtimes="${_src_dir}/../oganesson-mtimes.tsv"

# helium-linux's step, pruning only once per tree: pruning also removes the
# toolchains that setup_toolchain installs later.
apply_patches() {
    if [ ! -f "${_src_dir}/.patched.stamp" ]; then
        if [ ! -f "${_src_dir}/.pruned.stamp" ]; then
            "${_main_repo}/utils/prune_binaries.py" "${_src_dir}" "${_main_repo}/pruning.list"
            touch "${_src_dir}/.pruned.stamp"
        fi
        # Zero fuzz, as check-patches applies them: a hunk whose context
        # drifted fails here instead of landing somewhere else.
        "${_main_repo}/utils/patches.py" apply --no-fuzz "${_src_dir}" "${_main_repo}/patches" \
            "${_root_dir}/patches" /oganesson/patches
        touch "${_src_dir}/.patched.stamp"
    fi
}

# The output folder's GN arguments, kept once written. setup_toolchain reads
# them to decide whether to install the sysroot, which pruning removes.
write_args() {
    # Chromium 155 dropped this argument, which older dev trees still set.
    [ -f "${_out_dir}/args.gn" ] && sed -i '/^devtools_skip_typecheck/d' "${_out_dir}/args.gn"
    [ -f "${_out_dir}/args.gn" ] && return
    write_gn_args
    if [ "$mode" = dev ]; then
        # Same tweaks as helium-linux's dev.sh: component build for fast
        # incremental rebuilds.
        sed -i s/is_official_build/is_component_build/ "${_out_dir}/args.gn"
    else
        echo 'oganesson_x86_64_level = "x86-64-v2"' >> "${_out_dir}/args.gn"
    fi
}

# A tree prepared for other patches (a snapshot of the base tree, or an older
# series): back to the fetched sources, keeping downloads, toolchains and out/
# so the build stays incremental. Only files git knows as modified go back,
# and only untracked files git doesn't ignore go: the fetch leaves out test
# data, which stays out.
reset_tree() {
    echo "Resetting the source tree to the fetched sources"
    # A manifest left by a prepare that failed is from the last tree that built.
    [ -f "$_mtimes" ] || python3 /oganesson/tools/keep_mtimes.py save "$_src_dir" "$_mtimes"
    cd "$_src_dir"
    local repo
    while read -r repo; do
        repo="${repo%/.git}"
        git -C "$repo" diff --name-only -z --diff-filter=M |
            (cd "$repo" && xargs -0 -r git checkout --)
        git -C "$repo" clean -fdq -e /tools/gn -e /uc_staging -e /.downloaded.stamp
    done < <(find . -path ./out -prune -o -path ./uc_staging -prune -o -name .git -print)
    cd "$_src_dir"
    rm -f .patched.stamp .domsub.stamp "$stamp" "$_namesubs_cache"
    # Pruned files stay pruned: the reset doesn't bring back deleted files.
    touch .pruned.stamp
    rm -rf third_party/ublock components/helium_onboarding \
        third_party/search_engines_data/resources_internal
    "${_main_repo}/utils/downloads.py" retrieve -i "${_main_repo}/deps.ini" -c "${_dl_cache}"
    "${_main_repo}/utils/downloads.py" unpack -i "${_main_repo}/deps.ini" -c "${_dl_cache}" "${_src_dir}"
    cd - >/dev/null
}

# Fetched sources of another Chromium version than chromium_version.txt pins:
# reset_tree undoes the patches in every checkout, then fetch_sources moves
# the checkouts to the pin (clone.py fetches the new tag, gclient sync moves
# the dependencies; out/ stays, so the build is incremental), and the whole
# tree is prepared again. Git's HEAD holds the fetched version whatever the
# patches do to the working tree.
pin="$(cat "${_main_repo}/chromium_version.txt")"
if [ -f "${_src_dir}/.downloaded.stamp" ]; then
    fetched="$(git -C "$_src_dir" show HEAD:chrome/VERSION | cut -d= -f2 | paste -sd.)"
    if [ "$fetched" != "$pin" ]; then
        echo "The sources are Chromium ${fetched}; fetching ${pin}"
        reset_tree
        rm -f "${_src_dir}"/.downloaded.stamp "${_src_dir}"/.pruned.stamp \
            "${_src_dir}"/.patched.stamp "${_src_dir}"/.domsub.stamp "$stamp" "$_namesubs_cache"
    fi
fi

# The stamp's second field is the patch hash (oganesson.py's patch_hash, over
# every preparation input); the first is informational. A fetched tree without
# the stamp may be half patched from a failed build.
if [ -f "${_src_dir}/.downloaded.stamp" ] &&
    { [ ! -f "$stamp" ] || [ "$(cut -d' ' -f2 "$stamp")" != "$OGANESSON_PATCH_HASH" ]; }; then
    reset_tree
fi

if [ ! -f "$stamp" ]; then
    # Clone mode (git checkout of the Chromium tag): release tarballs are
    # often missing for new versions.
    fetch_sources true false
    # Our new files, which the patches then hook in: dubna's shared ones, then ours.
    cp -r /oganesson/dubna/src/. /oganesson/src/. "$_src_dir"
    apply_patches
    # After helium-linux's platform patches, which set the names these rename.
    "${_main_repo}/utils/patches.py" apply --no-fuzz "$_src_dir" /oganesson/late
    apply_domsub
    helium_substitution
    helium_apply_translations
    python3 /oganesson/dubna/tools/translate.py "$_src_dir" \
        /oganesson/dubna /oganesson
    # Helium -> oganesson in UI strings, after both steps above write them.
    python3 /oganesson/tools/branding.py "$_src_dir"
    # .gritdeps and resource ID sizes for our resources, once every step
    # that adds them has run.
    python3 /oganesson/tools/grit_fixups.py "$_src_dir"
    helium_version
    helium_resources
    fix_tool_downloading
    write_args
    setup_toolchain
    echo "tree ${OGANESSON_PATCH_HASH}" > "$stamp"
    if [ -f "$_mtimes" ]; then
        python3 /oganesson/tools/keep_mtimes.py restore "$_src_dir" "$_mtimes"
        rm -f "$_mtimes"
    fi
fi

write_args
if [ ! -f "${_out_dir}/build.ninja" ]; then
    (cd "$_src_dir" && ./buildtools/linux64/gn gen "$_out_dir" --fail-on-unused-args)
fi
cd "$_src_dir"
jobs=()
[ -n "${OGANESSON_JOBS:-}" ] && jobs=(-j "$OGANESSON_JOBS")
export SISO_PATH="${_src_dir}/third_party/siso/cipd/siso"
# Our own files first, new and patched (dubna/tools/ours.py): after a Chromium
# update, an API they use may be gone, and in the full build that error shows
# only near its end. -k 0: all of ours, then set -e stops on an error.
mapfile -t ours < <(python3 /oganesson/dubna/tools/ours.py "$_out_dir" \
    /oganesson/dubna/src /oganesson/src \
    $(for d in /oganesson/patches /oganesson/late; do sed "/^#/d;/^$/d;s|^|$d/|" "$d/series"; done))
[ ${#ours[@]} -eq 0 ] ||
    python3 third_party/depot_tools/autoninja.py -C "$_out_dir" "${jobs[@]}" -k 0 "${ours[@]}"
python3 third_party/depot_tools/autoninja.py -C "$_out_dir" "${jobs[@]}" -k 0 chrome
# Firefox Sync's Rust library, loaded by the browser from its folder.
level=""
[ "$mode" = release ] && level="x86-64-v2"
bash /oganesson/linux/build-sync-lib.sh "$_src_dir" build "$_out_dir" "$level"
