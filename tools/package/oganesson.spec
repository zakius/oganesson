# From helium-linux's package/helium-bin.spec, for oganesson's tarball. Built
# with debbuild for the .deb and rpmbuild for the .rpm (tools/package/package.sh).
%global debug_package %{nil}
%global __strip /bin/true
%global _build_id_links none

Name:    oganesson
Summary: Chromium browser with Firefox's add-ons, sync and comforts
Version: %{version}
Release: %{pkgrelease}%{?dist}
Group:   web
License: GPL-3.0
URL:     https://github.com/zakius/oganesson
Source0: %{tarball}.tar.xz

%if 0%{?debbuild}
Packager: oganesson
Provides: www-browser
# Given when the .deb is made on another architecture, where debbuild can't
# run ldd on the binaries: the Depends of the .deb made with the build.
%if 0%{?deb_depends:1}
Requires: %{deb_depends}
%endif
%endif

Recommends: ca-certificates, xdg-utils
%if 0%{?debbuild}
Recommends: fonts-liberation, libvulkan1
%else
Recommends: liberation-fonts, vulkan-loader
# Requires from the binaries' libraries, as dpkg-shlibdeps does for the .deb,
# except the ones the package carries and the Qt shims, which the browser
# loads only when Qt is installed. It provides no libraries to the system.
AutoProv: no
%global __requires_exclude_from ^/opt/oganesson/libqt[56]_shim\\.so$
%global __requires_exclude ^lib(EGL|GLESv2|vk_swiftshader|vulkan|oganesson_sync)\\.so
%endif

%description
A Chromium browser, built on Helium, with Firefox add-on compatibility,
Firefox Sync and Firefox quality-of-life features.

%prep
%setup -q -n %{tarball}

%build
# Prebuilt binaries.

%install
%define og_base /opt/oganesson
mkdir -p %{buildroot}%{og_base} %{buildroot}%{_bindir} \
         %{buildroot}%{_datadir}/applications \
         %{buildroot}%{_datadir}/icons/hicolor/256x256/apps
cp -a . %{buildroot}%{og_base}
%if 0%{?debbuild}
sed -Ei "s/(CHROME_VERSION_EXTRA=).*/\1deb/" %{buildroot}%{og_base}/oganesson-wrapper
%else
sed -Ei "s/(CHROME_VERSION_EXTRA=).*/\1rpm/" %{buildroot}%{og_base}/oganesson-wrapper
%endif
install -m 644 product_logo_256.png \
    %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/oganesson.png
install -m 644 oganesson.desktop %{buildroot}%{_datadir}/applications/
ln -sf %{og_base}/oganesson-wrapper %{buildroot}%{_bindir}/oganesson

%files
%defattr(-,root,root,-)
%{og_base}/
%{_bindir}/oganesson
%{_datadir}/applications/oganesson.desktop
%{_datadir}/icons/hicolor/256x256/apps/oganesson.png

%post
/usr/bin/update-desktop-database > /dev/null 2>&1 || :
/bin/touch --no-create %{_datadir}/icons/hicolor > /dev/null 2>&1 || :
if command -v apparmor_parser > /dev/null 2>&1 && [ -d /etc/apparmor.d ]; then
    cp %{og_base}/apparmor.cfg /etc/apparmor.d/oganesson
    apparmor_parser -r -W -T /etc/apparmor.d/oganesson || :
fi

%postun
/usr/bin/update-desktop-database > /dev/null 2>&1 || :
case "$1" in
    0|remove|purge)
        /usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor > /dev/null 2>&1 || :
        if [ -f /etc/apparmor.d/oganesson ]; then
            command -v apparmor_parser > /dev/null 2>&1 && \
                apparmor_parser -R /etc/apparmor.d/oganesson || :
            rm -f /etc/apparmor.d/oganesson
        fi
        ;;
esac

%posttrans
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor > /dev/null 2>&1 || :
