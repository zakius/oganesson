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
. /oganesson/tools/prepare.sh
setup_environment
_main_repo=/work/helium-tree
_root_dir=/oganesson/linux/helium-linux
_platform_late=/oganesson/linux/late
# The tree stays where the shared base tree has it (see oganesson.py
# snapshot): Siso's cache records absolute paths.
_build_dir=/work/helium-linux/build
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

# Release builds use Chromium's PGO profile, as helium-windows' do
# (chrome_pgo_phase=2 over Helium's 0): helium-linux's --pgo switch, which
# write_gn_args reads. clone.py fetches the profile (checkout_pgo_profiles).
[ "$mode" = release ] && _has_pgo=true

# The output folder's GN arguments: helium-linux's, then ours (flags.gn,
# linux/flags.gn). Rewritten each build; unchanged, the old file and its time
# stay, so gn doesn't run again.
write_args() {
    local args="${_out_dir}/args.gn"
    [ -f "$args" ] && mv "$args" "$args.old"
    write_gn_args >/dev/null
    cat /oganesson/flags.gn /oganesson/linux/flags.gn >> "$args"
    if [ "$mode" = dev ]; then
        # Same tweaks as helium-linux's dev.sh: component build for fast
        # incremental rebuilds.
        sed -i s/is_official_build/is_component_build/ "$args"
    else
        printf '%s\n' 'oganesson_x86_64_level = "x86-64-v2"' \
            'mojom_message_id_salt_path = "//chrome/MOJOM_SALT"' >> "$args"
    fi
    if cmp -s "$args" "$args.old"; then
        mv "$args.old" "$args"
    else
        rm -f "$args.old"
    fi
}

fetch_pinned linux
if [ ! -f "$stamp" ]; then
    prepare_tree
    mark_prepared
fi

write_args
if [ ! -f "${_out_dir}/build.ninja" ]; then
    (cd "$_src_dir" && ./buildtools/linux64/gn gen "$_out_dir" --fail-on-unused-args)
fi
cd "$_src_dir"
jobs=()
[ -n "${OGANESSON_JOBS:-}" ] && jobs=(-j "$OGANESSON_JOBS")
export SISO_PATH="${_src_dir}/third_party/siso/cipd/siso"
build_ours
python3 third_party/depot_tools/autoninja.py -C "$_out_dir" "${jobs[@]}" -k 0 chrome
# Firefox Sync's Rust library, loaded by the browser from its folder.
level=""
[ "$mode" = release ] && level="x86-64-v2"
bash /oganesson/linux/build-sync-lib.sh "$_src_dir" build "$_out_dir" "$level"
