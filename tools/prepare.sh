# Shared by linux/ and windows/container-build.sh, sourced after helium-linux's
# scripts/shared.sh (its platform-neutral steps) and after the script sets
# _main_repo (work/helium-tree), _root_dir (the platform's Helium repo:
# helium-linux or helium-windows), _build_dir, _src_dir, _dl_cache, _out_dir,
# _namesubs_cache, _mtimes and stamp; _platform_patches, when set, replaces
# the platform's patches folder; _platform_late, when set, is the platform's
# late series (linux/late).

# helium-linux's step: Helium's series, then the platform's and ours. Pruning
# keeps the build's tools that gclient fetched, and runs once per tree.
apply_patches() {
    if [ ! -f "${_src_dir}/.patched.stamp" ]; then
        if [ ! -f "${_src_dir}/.pruned.stamp" ]; then
            # The listed files the checkout has: a Windows checkout lacks Linux's
            # dependencies, which prune_binaries.py counts as failures.
            local listed
            listed="$(mktemp)"
            (cd "$_src_dir" && while read -r f; do if [ -e "$f" ]; then echo "$f"; fi; done) \
                < "${_main_repo}/pruning.list" > "$listed"
            "${_main_repo}/utils/prune_binaries.py" --keep-build-dependencies "${_src_dir}" "$listed"
            rm -f "$listed"
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
# data, which stays out. A repo's cipd/ stays too: in a Windows checkout,
# gclient puts the Linux host's gperf in third_party/gperf/cipd, inside
# gperf's own repo.
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
        git -C "$repo" clean -fdq -e /.downloaded.stamp -e /cipd/
    done < <(find . -path ./out -prune -o -name .git -print)
    cd "$_src_dir"
    rm -f .patched.stamp .domsub.stamp "$stamp" "$_namesubs_cache"
    # Pruned files stay pruned: the reset doesn't bring back deleted files.
    touch .pruned.stamp
    rm -rf third_party/ublock components/helium_onboarding \
        third_party/search_engines_data/resources_internal
    # The onboarding page's build adds to its dist/ in out/ and its .grd lists every file there,
    # so a new page's hashed files would come on top of the old page's.
    rm -rf out/*/gen/components/helium_onboarding
    "${_main_repo}/utils/downloads.py" retrieve -i "${_main_repo}/deps.ini" -c "${_dl_cache}"
    "${_main_repo}/utils/downloads.py" unpack -i "${_main_repo}/deps.ini" -c "${_dl_cache}" "${_src_dir}"
    cd - >/dev/null
}

# The sources at chromium_version.txt's pin, for PLATFORM (helium's clone.py
# -p: linux or win64): clone.py checks out the tag and gclient, with its hooks,
# the dependencies and the build's tools (clang, Rust, Node...), then Helium's
# deps.ini. A tree of another Chromium version is reset and moved in place,
# keeping out/, so the build stays incremental (Git's HEAD holds the fetched
# version whatever the patches do). A tree prepared for other inputs, or half
# prepared by a failed build, is reset; the stamp's second field is the inputs'
# hash (oganesson.py's patch_hash), its first is informational. Without the
# stamp after this, the tree needs preparing (prepare_tree, then mark_prepared).
fetch_pinned() {
    local pin fetched
    pin="$(cat "${_main_repo}/chromium_version.txt")"
    if [ -f "${_src_dir}/.downloaded.stamp" ]; then
        fetched="$(git -C "$_src_dir" show HEAD:chrome/VERSION | cut -d= -f2 | paste -sd.)"
        if [ "$fetched" != "$pin" ]; then
            echo "The sources are Chromium ${fetched}; fetching ${pin}"
            reset_tree
            rm -f "${_src_dir}"/.downloaded.stamp "${_src_dir}"/.pruned.stamp "$stamp"
        fi
    fi
    echo "Inputs ${OGANESSON_PATCH_HASH}; the tree's: $(cut -d' ' -f2 "$stamp" 2>/dev/null)"
    if [ -f "${_src_dir}/.downloaded.stamp" ] &&
        { [ ! -f "$stamp" ] || [ "$(cut -d' ' -f2 "$stamp")" != "$OGANESSON_PATCH_HASH" ]; }; then
        reset_tree
    fi
    if [ ! -f "${_src_dir}/.downloaded.stamp" ]; then
        "${_main_repo}/utils/clone.py" -o "$_src_dir" -p "$1"
        "${_main_repo}/utils/downloads.py" retrieve -i "${_main_repo}/deps.ini" -c "${_dl_cache}"
        "${_main_repo}/utils/downloads.py" unpack -i "${_main_repo}/deps.ini" -c "${_dl_cache}" \
            "${_src_dir}"
        touch "${_src_dir}/.downloaded.stamp"
    fi
}

# The tree is prepared for these inputs; unchanged files get their times back
# (tools/keep_mtimes.py), so only what changed rebuilds.
mark_prepared() {
    echo "tree ${OGANESSON_PATCH_HASH}" > "$stamp"
    if [ -f "$_mtimes" ]; then
        python3 /oganesson/tools/keep_mtimes.py restore "$_src_dir" "$_mtimes"
        rm -f "$_mtimes"
    fi
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
    # Mojo's message ID salt (mojom_message_id_salt_path, set by the platforms'
    # official builds): the Chromium milestone, not all of chrome/VERSION, so the
    # IDs change once a milestone and a patch release or rebuild doesn't
    # regenerate every mojom header (about 4,400 of 5,150 build steps).
    # keep_mtimes.py keeps the file's time while its content stays.
    grep '^MAJOR=' "$_src_dir/chrome/VERSION" > "$_src_dir/chrome/MOJOM_SALT"
    # The platform's own resources (a platform_resources function) first, then
    # Helium's, as helium-windows' build.py copies them.
    ! declare -F platform_resources >/dev/null || platform_resources
    helium_resources
}

# Our own files first, new and patched (dubna/tools/ours.py): after a Chromium
# update, an API they use may be gone, and in the full build that error shows
# only near its end. -k 0: all of ours, then set -e stops on an error. Run in
# the tree, with jobs set. gn writes the build files again first: ours.py reads
# them, and after a prepare they may still be the last tree's.
build_ours() {
    local -a ours
    ./buildtools/linux64/gn gen "$_out_dir"
    mapfile -t ours < <(python3 /oganesson/dubna/tools/ours.py "$_out_dir" \
        /oganesson/dubna/src /oganesson/src \
        $(for d in /oganesson/patches /oganesson/late ${_platform_late:-}; do sed "/^#/d;/^$/d;s|^|$d/|" "$d/series"; done))
    [ ${#ours[@]} -eq 0 ] ||
        python3 third_party/depot_tools/autoninja.py -C "$_out_dir" "${jobs[@]}" -k 0 "${ours[@]}"
}

# Copies FILE into FOLDER with its time, under its name only once it is whole:
# a build stopped mid-copy leaves no truncated profile to be trusted later.
copy_whole() {
    cp -p "$1" "$2/.$(basename "$1").part"
    mv "$2/.$(basename "$1").part" "$2/$(basename "$1")"
}

# A release build's PGO profile, for TARGET (linux or win64; docs/updating.md,
# "PGO profiles"). Every compile reads it, and Chromium ships a new one with
# each release, so a new profile rebuilds everything. Within a milestone the
# build keeps the profile pgo-profiles.txt pins: prints the GN argument that
# points at it when the tree's own differs, and nothing for the tree's own.
# The branch number after the target names the milestone. A copy in the build
# folder outlives Chromium's pruning of unused profiles, and cp -p keeps its
# time, so the compiles that read it don't rerun.
pinned_pgo_profile() {
    local target="$1" own pin
    local profiles="${_src_dir}/chrome/build/pgo_profiles" kept="${_build_dir}/pgo-profiles"
    own="$(cat "${_src_dir}/chrome/build/${target}.pgo.txt")"
    pin="$(awk -v target="$target" '$1 == target { print $2 }' /oganesson/pgo-profiles.txt)"
    mkdir -p "$kept"
    if [ -n "$pin" ] && [ -f "${profiles}/${pin}" ] && [ ! -f "${kept}/${pin}" ]; then
        copy_whole "${profiles}/${pin}" "${kept}"
    fi
    if [ "$pin" = "$own" ]; then
        return
    fi
    if [ -z "$pin" ] || [ "$(echo "$pin" | cut -d- -f3)" != "$(echo "$own" | cut -d- -f3)" ]; then
        echo "PGO: the tree's own profile, ${own}: the pinned one, ${pin:-none}, is another milestone's" >&2
        return
    fi
    if [ ! -f "${kept}/${pin}" ]; then
        echo "PGO: the tree's own profile, ${own}: the pinned ${pin} is missing, so everything rebuilds" >&2
        return
    fi
    [ -f "${profiles}/${pin}" ] || copy_whole "${kept}/${pin}" "${profiles}"
    echo "PGO: the pinned profile, ${pin}, over the tree's ${own}" >&2
    echo "pgo_data_path = \"//chrome/build/pgo_profiles/${pin}\""
}
