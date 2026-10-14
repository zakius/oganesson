# helium-linux's packager image (appimagetool, debbuild), plus rpmbuild, and
# createrepo_c and apt-ftparchive for linux/publish-repo.sh.
ARG BASE=helium-chromium-trixie-slim:packager
FROM ${BASE}
USER root
RUN apt -y update && apt -y install --no-install-recommends rpm createrepo-c apt-utils
USER builder
