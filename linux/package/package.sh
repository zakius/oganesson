#!/usr/bin/env bash
# Packages a release build. Based on helium-linux's scripts/package.sh.
#
#   package.sh <out folder> <target> <format>...
#
# formats: tarball and rpm run in the rpm.Dockerfile image, deb in the
# deb.Dockerfile image. Output: $PACKAGES, default work/packages/
# The deb and rpm are made from the tarball: the one made in the same run, or
# TARBALL (a tarball this script made), and then <out folder> is unused.
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
version=$(cat "$repo/helium/chromium_version.txt")
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
    product_logo_256.png app_icons"

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

    # The x86 filter makes the binary's calls and jumps compress better:
    # about 1% off the archive, more than -9e alone gains.
    tar -C "$stage" -cf - "$tarball" | xz -T0 --x86 --lzma2=preset=9e > "$stage/$tarball.tar.xz"
    if want tarball; then
        cp "$stage/$tarball.tar.xz" "$packages/"
    fi
fi

if want deb; then
    # dpkg-shlibdeps finds the package's own files under debian/<package>,
    # whose DEBIAN folder marks the root.
    root="$stage/debian/oganesson"
    base="$root/opt/oganesson"
    mkdir -p "$root/DEBIAN" "$root/opt" "$root/usr/bin" "$root/usr/share/applications" \
        "$root/usr/share/metainfo" "$root/usr/share/icons/hicolor/256x256/apps"
    tar -C "$root/opt" -xf "$stage/$tarball.tar.xz"
    mv "$root/opt/$tarball" "$base"
    sed -Ei 's/(CHROME_VERSION_EXTRA=).*/\1deb/' "$base/oganesson-wrapper"
    ln -s ../../opt/oganesson/oganesson-wrapper "$root/usr/bin/oganesson"
    install -m 644 "$base/oganesson.desktop" "$root/usr/share/applications/"
    install -m 644 "$base/product_logo_256.png" \
        "$root/usr/share/icons/hicolor/256x256/apps/oganesson.png"
    install -m 644 "$linux/package/oganesson.metainfo.xml" \
        "$root/usr/share/metainfo/io.github.zakius.oganesson.metainfo.xml"

    # The libraries the binaries link, except the Qt shims, which the
    # browser loads only when Qt is installed. The ones the package
    # carries are found under $root and left out. GTK is loaded at run
    # time, so no binary links it.
    # --warnings=1 leaves out "could avoid a useless dependency" only: the
    # build links against Chromium's sysroot, whose glibc 2.31 still has
    # pthread and dl functions in libpthread.so.0 and libdl.so.2. Since
    # glibc 2.34 they are in libc.so.6, and all three are libc6's.
    printf 'Source: oganesson\n\nPackage: oganesson\nArchitecture: amd64\n' \
        > "$stage/debian/control"
    elves=()
    while read -r elf; do
        elves+=("-e$elf")
    done < <(find "$base" -type f ! -name 'libqt*_shim.so' -exec file {} + \
        | awk -F: '/ELF/ {print $1}')
    shlibs="$(cd "$stage" && DEB_HOST_ARCH=amd64 DEB_HOST_GNU_TYPE=x86_64-linux-gnu \
        DEB_HOST_MULTIARCH=x86_64-linux-gnu dpkg-shlibdeps -O --warnings=1 "${elves[@]}")"
    cat > "$root/DEBIAN/control" <<EOF
Package: oganesson
Version: ${version}-${PKG_RELEASE:-1}
Architecture: amd64
Maintainer: oganesson
Installed-Size: $(du -sk --exclude=DEBIAN "$root" | cut -f1)
Section: web
Priority: optional
Homepage: https://github.com/zakius/oganesson
Provides: www-browser
Depends: ${shlibs#shlibs:Depends=}, libgtk-3-0t64 | libgtk-4-1
Recommends: ca-certificates, xdg-utils, fonts-liberation, libvulkan1
Description: Chromium browser with mouse gestures and Firefox Sync
 A desktop Chromium browser built on Helium. It adds mouse gestures, a toolbar
 whose items move and hide, and Firefox tab placement and close selection. It
 also has Firefox-compatible Sync, controls for installed web apps, and
 switches that stop saving history.
EOF
    # The desktop database and icon cache are updated by dpkg triggers of
    # desktop-file-utils and the icon themes; only the AppArmor profile is ours.
    cat > "$root/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ] && command -v apparmor_parser > /dev/null 2>&1 \
        && [ -d /etc/apparmor.d ]; then
    cp /opt/oganesson/apparmor.cfg /etc/apparmor.d/oganesson
    apparmor_parser -r -W -T /etc/apparmor.d/oganesson || :
fi
EOF
    cat > "$root/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if { [ "$1" = remove ] || [ "$1" = purge ]; } && [ -f /etc/apparmor.d/oganesson ]; then
    if command -v apparmor_parser > /dev/null 2>&1; then
        apparmor_parser -R /etc/apparmor.d/oganesson || :
    fi
    rm -f /etc/apparmor.d/oganesson
fi
EOF
    chmod 755 "$root/DEBIAN/postinst" "$root/DEBIAN/postrm"
    # xz -9: dpkg-deb's default -6 makes the .deb about 4 MB bigger. The tier
    # goes in the file name; both tiers are the same package.
    dpkg-deb --root-owner-group -Zxz -z9 --build "$root" \
        "$packages/oganesson_${version}-${target}_amd64.deb" > /dev/null
fi

if want rpm; then
    top="$stage/rpm"
    mkdir -p "$top"/{BUILD,SOURCES,SPECS,RPMS}
    ln -sf "$stage/$tarball.tar.xz" "$top/SOURCES/"
    cp "$linux/package/oganesson.metainfo.xml" "$top/SOURCES/"
    # xz -9, multithreaded: about 10 MB smaller than Fedora's own zstd -19, for a
    # few seconds more unpacking at install. The spec has no %changelog to take
    # file times from.
    rpmbuild --quiet --define "_topdir $top" --define "version ${version}" \
        --define "pkgrelease ${PKG_RELEASE:-1}" --define "tarball $tarball" \
        --define "dist %{nil}" --define "_binary_payload w9T0.xzdio" \
        --define "source_date_epoch_from_changelog 0" \
        --target x86_64 -bb "$linux/package/oganesson.spec"
    mv "$top"/RPMS/*/*.rpm "$packages/oganesson-${version}-${target}.x86_64.rpm"
fi
