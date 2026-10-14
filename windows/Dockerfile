# The Windows cross build's image: the Linux builder (helium-linux's
# docker/build.Dockerfile, tagged oganesson-builder) and what Windows adds:
# ciopfs, the case-insensitive mount Chromium puts the toolchain in, and NSIS
# for the installer.
FROM oganesson-builder
USER root
RUN apt-get -y update && apt-get -y install ciopfs fuse3 nsis && apt-get clean
USER builder
