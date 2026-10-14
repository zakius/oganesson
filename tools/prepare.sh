# Shared by linux/ and windows/container-build.sh, sourced after helium-linux's
# scripts/shared.sh (its platform-neutral steps) and after the script sets
# _main_repo (work/helium-tree), _root_dir (the platform's Helium repo:
# helium-linux or helium-windows), _build_dir, _src_dir, _dl_cache, _out_dir,
# _namesubs_cache, _mtimes and stamp; _platform_patches, when set, replaces
# the platform's patches folder; _platform_late, when set, is the platform's
# late series (linux/late).

# helium-linux's step: Helium's series, then the platform's and ours. Pruning
# runs once per tree, as it also removes the toolchains setup_toolchain installs.
apply_patches() {
    if [ ! -f "${_src_dir}/.patched.stamp" ]; then
        if [ ! -f "${_src_dir}/.pruned.stamp" ]; then
            "${_main_repo}/utils/prune_binaries.py" "${_src_dir}" "${_main_repo}/pruning.list"
            touch "${_src_dir}/.pruned.stamp"
        fi
        # Zero fuzz, as check-patches applies them: a hunk whose context
        # drifted fails here instead of landing somewhere else.
        "${_main_repo}/utils/patches.py" apply --no-fuzz "${_src_dir}" "${_main_repo}/patches" \
            "${_platform_patches:-${_root_dir}/patches}" /oganesson/patches
        touch "${_src_dir}/.patched.stamp"
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

# Our files and patches, then Helium's steps that write over the tree.
prepare_tree() {
    # Our new files, which the patches then hook in: dubna's shared ones, then ours.
    cp -r /oganesson/dubna/src/. /oganesson/src/. "$_src_dir"
    apply_patches
    # After the platform patches, which set the names these rename.
    "${_main_repo}/utils/patches.py" apply --no-fuzz "$_src_dir" /oganesson/late
    # The platform's: renames of what its Helium repo's patches set.
    [ -z "${_platform_late:-}" ] ||
        "${_main_repo}/utils/patches.py" apply --no-fuzz "$_src_dir" "$_platform_late"
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
}

# Our own files first, new and patched (dubna/tools/ours.py): after a Chromium
# update, an API they use may be gone, and in the full build that error shows
# only near its end. -k 0: all of ours, then set -e stops on an error. Run in
# the tree, with jobs set. gn writes the build files again first: ours.py reads
# them, and after a prepare they may still be the last tree's.
build_ours() {
    local -a ours
    ./buildtools/linux64/gn gen "$_out_dir" >/dev/null
    mapfile -t ours < <(python3 /oganesson/dubna/tools/ours.py "$_out_dir" \
        /oganesson/dubna/src /oganesson/src \
        $(for d in /oganesson/patches /oganesson/late ${_platform_late:-}; do sed "/^#/d;/^$/d;s|^|$d/|" "$d/series"; done))
    [ ${#ours[@]} -eq 0 ] ||
        python3 third_party/depot_tools/autoninja.py -C "$_out_dir" "${jobs[@]}" -k 0 "${ours[@]}"
}
