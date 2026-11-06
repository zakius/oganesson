# The .deb packager image (linux/package/package.sh's deb), also
# apt-ftparchive for linux/package/repo-build.sh. The .deb's Depends come from
# dpkg-shlibdeps against these libraries, whose versions become the minimum
# ones, so the image is the oldest release the .deb supports: Ubuntu 24.04,
# the first with the t64 package names that Debian 13 also has.
FROM docker.io/library/ubuntu:24.04
RUN apt-get -y update && apt-get -y install --no-install-recommends \
        apt-utils dpkg-dev file xz-utils \
        libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 libcairo2 \
        libcups2t64 libdbus-1-3 libdrm2 libexpat1 libgbm1 libglib2.0-0t64 libnspr4 libnss3 \
        libpango-1.0-0 libudev1 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 \
        libxfixes3 libxkbcommon0 libxrandr2 \
    && rm -rf /var/lib/apt/lists/*
# libc6 diverts /lib64/ld-linux-x86-64.so.2 for the /usr merge; the file is the
# same either way. dpkg-shlibdeps looks the loader up there too and warns
# about any diversion it meets, so the image drops the record (not the file).
RUN dpkg-divert --package libc6 --no-rename --remove /lib64/ld-linux-x86-64.so.2
