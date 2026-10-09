# helium-linux's packager image (appimagetool, debbuild), plus rpmbuild.
ARG BASE=helium-chromium-trixie-slim:packager
FROM ${BASE}
USER root
RUN apt -y update && apt -y install --no-install-recommends rpm
USER builder
