# The tarball and .rpm packager image (linux/package/package.sh's tarball and
# rpm), also createrepo_c for linux/package/repo-build.sh: Fedora's own rpmbuild
# and dependency generators.
FROM registry.fedoraproject.org/fedora:45
RUN dnf -y install --setopt=install_weak_deps=False binutils createrepo_c file rpm-build xz \
    && dnf clean all
