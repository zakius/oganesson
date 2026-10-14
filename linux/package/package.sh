#!/usr/bin/env bash
# Packages a release build (runs in the packager container, see Dockerfile).
# Based on helium-linux's scripts/package.sh and package/mkdeb.sh.
#
#   package.sh <out folder> <target> <format>...
#
# formats: tarball appimage deb rpm. Output: $PACKAGES, default work/packages/
# With TARBALL (a tarball this script made) and VERSION, the deb and rpm are
# made from that tarball and <out folder> is unused: linux/publish-repo.sh
# packages this way on the repository server, an arm64 host. There, DEPENDS
# (the Depends of the .deb made with the build) replaces debbuild's ldd scan.
set -euo pipefail

out="$(realpath "$1")"
target="$2"
shift 2
formats=("$@")

repo=/oganesson
linux="$repo/linux"
# helium-linux's packaging files (the linux/helium-linux submodule).
helium_linux="$linux/helium-linux"
packages="${PACKAGES:-$repo/work/packages}"
# The version the build itself carries (chrome/VERSION): the vendored files,
# the same ones as the packaging files.
version=${VERSION:-$(python3 "$repo/helium/utils/helium_version.py" \
    --tree "$repo/helium" --platform-tree "$helium_linux" --print)}
name="oganesson-${version}-x86_64-${target}"
tarball="${name}_linux"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$packages"
want() { [[ " ${formats[*]} " == *" $1 "* ]]; }

if [ -n "${TARBALL:-}" ]; then
    tarball="$(basename "$TARBALL" .tar.xz)"
    ln -s "$(realpath "$TARBALL")" "$stage/$tarball.tar.xz"
else
    # Helium also ships xdg-mime and xdg-settings; this build doesn't make them,
    # and the browser uses the system's (xdg-utils, which the packages recommend).
    files="oganesson oganesson_crashpad_handler chrome_100_percent.pak
    chrome_200_percent.pak resources.pak icudtl.dat v8_context_snapshot.bin
    libEGL.so libGLESv2.so libqt5_shim.so libqt6_shim.so libvk_swiftshader.so
    libvulkan.so.1 vk_swiftshader_icd.json liboganesson_sync.so
    product_logo_256.png"

    dir="$stage/$tarball"
    mkdir -p "$dir/locales"
    for file in $files; do
        cp -a "$out/$file" "$dir/"
    done
    cp "$out/locales/"*.pak "$dir/locales/"
    cp "$repo/resources/oganesson.desktop" "$dir/"
    sed 's/helium/oganesson/g' "$helium_linux/package/apparmor.cfg" > "$dir/apparmor.cfg"
    sed -e 's|"\$HERE/helium"|"$HERE/oganesson"|' -e 's/Helium/oganesson/g' \
        "$helium_linux/package/helium-wrapper.sh" > "$dir/oganesson-wrapper"
    chmod 755 "$dir/oganesson-wrapper"
    ln -sf oganesson "$dir/chrome"
    find "$dir" -type f -exec file {} + | awk -F: '/ELF/ {print $1}' \
        | xargs strip --strip-unneeded

    if want tarball || want deb || want rpm; then
        tar -C "$stage" -cf - "$tarball" | xz -T0 -9 > "$stage/$tarball.tar.xz"
    fi
    if want tarball; then
        cp "$stage/$tarball.tar.xz" "$packages/"
    fi
fi

if want appimage; then
    app="$stage/oganesson.AppDir"
    mkdir -p "$app/opt/oganesson" "$app/usr/share/icons/hicolor/256x256/apps"
    cp -a "$dir/." "$app/opt/oganesson/"
    cp "$repo/resources/oganesson.desktop" "$app/"
    sed -e 's|/opt/helium/helium|/opt/oganesson/oganesson|' \
        -e 's/helium-appimage/oganesson-appimage/g' -e 's/Helium/oganesson/g' \
        "$helium_linux/package/helium-wrapper-appimage.sh" > "$app/AppRun"
    chmod 755 "$app/AppRun"
    cp "$dir/product_logo_256.png" "$app/oganesson.png"
    cp "$dir/product_logo_256.png" "$app/usr/share/icons/hicolor/256x256/apps/oganesson.png"
    # No update information: oganesson has no update feed.
    APPIMAGETOOL_APP_NAME=oganesson VERSION="$version" \
        appimagetool "$app" "$packages/$name.AppImage"
fi

spec() {  # <tool> <topdir> [defines...]
    local tool="$1" top="$2"
    shift 2
    mkdir -p "$top"/{BUILD,SOURCES,SPECS,DEBS,RPMS}
    ln -sf "$stage/$tarball.tar.xz" "$top/SOURCES/"
    "$tool" --define "_topdir $top" --define "version ${version}" \
        --define "pkgrelease ${PKG_RELEASE:-1}" \
        --define "tarball $tarball" "$@" -bb "$repo/linux/package/oganesson.spec"
}
if want deb; then
    depends=()
    if [ -n "${DEPENDS:-}" ]; then
        depends=(--define "deb_depends $DEPENDS" --define "__ldd true")
    fi
    spec debbuild "$stage/deb" --define "debbuild 1" --define "_arch amd64" \
        --define "dist %{nil}" "${depends[@]}"
    # The tier goes in the file name; both tiers are the same package.
    mv "$stage"/deb/DEBS/*/*.deb "$packages/oganesson_${version}-${target}_amd64.deb"
fi
if want rpm; then
    spec rpmbuild "$stage/rpm" --define "dist %{nil}" --target x86_64
    mv "$stage"/rpm/RPMS/*/*.rpm "$packages/oganesson-${version}-${target}.x86_64.rpm"
fi
ls -l "$packages"
