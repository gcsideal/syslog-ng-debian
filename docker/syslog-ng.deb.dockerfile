#############################################################################
# Copyright (c) 2015-2023 Balabit
# Copyright (c) 2024 One Identity LLC.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
# As an additional exemption you are allowed to compile & link against the
# OpenSSL libraries as published by the OpenSSL project. See the file
# COPYING for details.
#
#############################################################################

# Declare the BASE_IMAGE ARG first!
ARG BASE_IMAGE=debian:trixie

FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.authors="kira.syslogng@gmail.com"
LABEL org.opencontainers.image.source="https://github.com/syslog-ng/syslog-ng"

# redeclare ARGs so they are available after FROM
ARG BASE_IMAGE
ARG PKG_TYPE=stable
ARG PACKAGE_VERSION
ARG CONTAINER_ARCH=amd64
ARG CONTAINER_NAME_SUFFIX

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && \
    apt-get upgrade -y && \
    apt-get install -y \
        wget \
        ca-certificates \
        gnupg2 \
        lz4 && \
    rm -rf /var/lib/apt/lists/*

# See .github/workflows/publish-docker-image.yml for why cannot use the ARG versions of these here currenty.
RUN ARCH=$(arch) && \
  if [ "$ARCH" = "aarch64" ]; then \
    CONTAINER_ARCH="arm64"; CONTAINER_NAME_SUFFIX="-arm64"; \
  else \
    CONTAINER_ARCH="amd64"; CONTAINER_NAME_SUFFIX=""; \
  fi && \
  DISTRO=${BASE_IMAGE%%:*} && \
  CODENAME=${BASE_IMAGE#*:} && \
  set -o pipefail && \
  wget -qO - https://ose-repo.syslog-ng.com/apt/syslog-ng-ose-pub.asc | gpg --dearmor -o /usr/share/keyrings/ose-repo-archive-keyring.gpg && \
  echo "deb [signed-by=/usr/share/keyrings/ose-repo-archive-keyring.gpg arch=$CONTAINER_ARCH] https://ose-repo.syslog-ng.com/apt/ ${PKG_TYPE} ${DISTRO}-${CODENAME}$CONTAINER_NAME_SUFFIX" | tee --append /etc/apt/sources.list.d/syslog-ng-ose.list && \
  apt-get update -qq && \
  # Enumerate the base package + every published syslog-ng-mod-* package
  # directly from the OSE repository's Packages index (NOT via apt-cache
  # search, which would also match same-named packages in Debian's own
  # repos and could drag in module packages OSE doesn't ship).
  # Java-related modules (java, java-common-lib, hdfs) are excluded to keep
  # the image lean — pulling OpenJDK would roughly double the image size.
  # Modern apt downloads Packages.lz4, so we decompress with lz4cat.
  OSE_PKGS_FILE="$(ls /var/lib/apt/lists/ose-repo.syslog-ng.com_*_dists_${PKG_TYPE}_${DISTRO}-${CODENAME}${CONTAINER_NAME_SUFFIX}_binary-${CONTAINER_ARCH}_Packages* 2>/dev/null | head -n1)" && \
  [ -n "$OSE_PKGS_FILE" ] && [ -r "$OSE_PKGS_FILE" ] || { echo "ERROR: OSE Packages index not found under /var/lib/apt/lists/" >&2; ls /var/lib/apt/lists/ >&2; exit 1; } && \
  echo "Using OSE Packages index: $OSE_PKGS_FILE" && \
  case "$OSE_PKGS_FILE" in \
    *.lz4) CAT=lz4cat ;; \
    *.gz)  CAT=zcat ;; \
    *.xz)  CAT=xzcat ;; \
    *)     CAT=cat ;; \
  esac && \
  # Materialise (name, version) pairs from the OSE Packages index once so
  # we can resolve a single target version and filter the subpackage set
  # against it. Pinning the whole set to a single version is required
  # because nightly builds occasionally don't republish every subpackage
  # in lock-step (e.g. when a module is added / removed / temporarily
  # skipped). The strict `Depends: syslog-ng (= <ver>)` of any stale
  # leftover would otherwise drag in a mismatched base package and make
  # apt's resolution unsatisfiable.
  ALL_PKGS="$($CAT "$OSE_PKGS_FILE" | awk 'BEGIN { RS=""; FS="\n" } { name=""; version=""; for (i=1;i<=NF;i++) { if ($i ~ /^Package: /) name=substr($i,10); if ($i ~ /^Version: /) version=substr($i,10) } if (name!="" && version!="") print name " " version }')" && \
  if [ -n "$PACKAGE_VERSION" ]; then \
    RESOLVED_VERSION="$PACKAGE_VERSION"; \
    echo "Installing locked syslog-ng version: $RESOLVED_VERSION"; \
  else \
    RESOLVED_VERSION="$(echo "$ALL_PKGS" | awk '$1 == "syslog-ng" { print $2 }' | sort -V -r | head -n1)"; \
    [ -n "$RESOLVED_VERSION" ] || { echo "ERROR: could not resolve newest syslog-ng version from OSE Packages index" >&2; exit 1; }; \
    echo "Installing newest syslog-ng version: $RESOLVED_VERSION"; \
  fi && \
  # Enumerate the base package + every syslog-ng-mod-* package that
  # exists at the resolved version. Java-related modules (java,
  # java-common-lib, hdfs) are excluded to keep the image lean — pulling
  # OpenJDK would roughly double the image size. Modules without a build
  # at the resolved version (e.g. ones intentionally dropped this round)
  # are simply not enumerated, which is the correct behaviour.
  SYSLOG_PKGS="$(echo "$ALL_PKGS" \
      | awk -v ver="$RESOLVED_VERSION" '$2 == ver { print $1 }' \
      | grep -E '^(syslog-ng|syslog-ng-mod-.*)$' \
      | grep -Ev '^syslog-ng-mod-(java|java-common-lib|hdfs)$' \
      | sort -u)" && \
  if [ -z "$SYSLOG_PKGS" ]; then echo "ERROR: no syslog-ng packages found at version $RESOLVED_VERSION in OSE Packages index" >&2; exit 1; fi && \
  SYSLOG_PKGS="$(echo "$SYSLOG_PKGS" | sed "s/\$/=${RESOLVED_VERSION}/")" && \
  apt-get install -y \
    libdbd-mysql libdbd-pgsql libdbd-sqlite3 libjemalloc2 \
    $SYSLOG_PKGS \
  && \
  # Drop build-only tooling (and anything pulled in transitively) plus apt /
  # debconf caches and logs so the final image stays as lean as possible.
  # ca-certificates is intentionally kept — syslog-ng needs the trust store
  # at runtime for TLS destinations.
  apt-get purge -y --auto-remove wget gnupg2 lz4 \
  && rm -rf /var/lib/apt/lists/* /var/log/apt/* /var/log/dpkg.log \
            /var/cache/debconf/*-old /tmp/* /var/tmp/*

COPY syslog-ng.conf /etc/syslog-ng/syslog-ng.conf

EXPOSE 514/udp
EXPOSE 601/tcp
EXPOSE 6514/tcp

HEALTHCHECK --interval=2m --timeout=5s --start-period=30s CMD /usr/sbin/syslog-ng-ctl healthcheck --timeout 5

ENV LD_PRELOAD=""

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
