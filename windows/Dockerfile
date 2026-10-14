# The Windows cross build's image: the Linux builder (helium-linux's
# docker/build.Dockerfile, tagged oganesson-builder) and what Windows adds:
# ciopfs, the case-insensitive mount Chromium puts the toolchain in (built here:
# Debian dropped it, and Chromium's prebuilt one needs a library Debian dropped
# too), FUSE, NSIS and 7-Zip for the installer and zstd for MSYS2's NSS packages.
FROM oganesson-builder
USER root
RUN apt-get -y update && apt-get -y install fuse libfuse2t64 libfuse-dev libglib2.0-dev \
      libattr1-dev nsis zstd 7zip && apt-get clean
RUN cd /tmp && curl -sfLO https://www.brain-dump.org/projects/ciopfs/ciopfs-0.4.tar.gz && \
    echo "34d5553e519cc363f76c7435256d98b88b3e5ece1e80b9ff768b3b3c568a296b  ciopfs-0.4.tar.gz" | sha256sum -c && \
    tar xzf ciopfs-0.4.tar.gz && make -C ciopfs-0.4 && \
    install -m 755 ciopfs-0.4/ciopfs /usr/local/bin/ && rm -rf /tmp/ciopfs-0.4*
USER builder
