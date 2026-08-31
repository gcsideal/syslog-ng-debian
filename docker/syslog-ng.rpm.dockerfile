#############################################################################
# Copyright (c) 2026 One Identity LLC.
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
ARG BASE_IMAGE=almalinux:9

FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.authors="kira.syslogng@gmail.com"
LABEL org.opencontainers.image.source="https://github.com/syslog-ng/syslog-ng"

# Redeclare ARGs so they are available after FROM
ARG BASE_IMAGE
ARG PKG_TYPE=stable
ARG PACKAGE_VERSION

# Ensure the syslog-ng binaries (installed under /usr/sbin and /usr/bin) are
# always reachable. systemd-as-PID-1 does not propagate the image's PATH to
# `docker exec` sessions, and the almalinux:9 base ships a narrower default
# PATH than debian — so set it explicitly here for parity with the DEB image.
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

#
# Stage 1: install systemd and prepare it for in-container init.
# Strip unit dependencies that are meaningless inside a container so that
# `systemd` can come up cleanly as PID 1.
#
RUN dnf -y install systemd procps-ng && \
    dnf clean all && \
    (cd /lib/systemd/system/sysinit.target.wants/; for i in *; do [ "$i" = systemd-tmpfiles-setup.service ] || rm -f "$i"; done) && \
    rm -f /lib/systemd/system/multi-user.target.wants/* \
          /etc/systemd/system/*.wants/* \
          /lib/systemd/system/local-fs.target.wants/* \
          /lib/systemd/system/sockets.target.wants/*udev* \
          /lib/systemd/system/sockets.target.wants/*initctl* \
          /lib/systemd/system/basic.target.wants/* \
          /lib/systemd/system/anaconda.target.wants/*

#
# Stage 2: install the syslog-ng OSE RPM (and only its runtime dependencies)
# from the official yum repository. The base AlmaLinux 9 image already ships
# `curl-minimal` (providing the `curl` command) and `ca-certificates`, so no
# extra bootstrap tooling needs to be installed — and intentionally nothing
# pre-existing in the base image is removed afterwards.
#
# EPEL is enabled because several runtime dependencies of the syslog-ng OSE
# RPM (e.g. `ivykis`) are only published there, not in the AlmaLinux base
# repositories. `jemalloc` is also pulled from EPEL and preloaded into
# syslog-ng for better allocator behaviour under sustained load (mirrors
# what the Debian image does via its entrypoint wrapper).
#
# CRB (CodeReady Builder) is also enabled because several EPEL packages
# pulled in transitively (notably `grpc-cpp`, needed by the gRPC-based
# syslog-ng modules) depend on libraries that only live in CRB.
#
RUN set -eu -o pipefail && \
    dnf -y install --setopt=install_weak_deps=False epel-release dnf-plugins-core && \
    dnf config-manager --set-enabled crb && \
    curl -fsSL -o /etc/yum.repos.d/syslog-ng-ose.repo \
        "https://ose-repo.syslog-ng.com/yum/syslog-ng-ose-${PKG_TYPE}.repo" && \
    dnf -y makecache && \
    # Determine the OSE repo id from the just-written .repo file so we can
    # constrain enumeration / installation to it. This avoids pulling in
    # EPEL's ancient `syslog-ng-3.35` (and its `syslog-ng-snmp` subpackage),
    # which would otherwise conflict with the current OSE 4.x packages.
    OSE_REPO_ID="$(grep -oE '^\[[^]]+\]' /etc/yum.repos.d/syslog-ng-ose.repo | head -n1 | tr -d '[]')" && \
    [ -n "$OSE_REPO_ID" ] || { echo "ERROR: could not determine OSE repo id" >&2; exit 1; } && \
    echo "Using OSE repo id: $OSE_REPO_ID" && \
    # Resolve the exact EVR to install. If the caller pinned PACKAGE_VERSION,
    # honour it; otherwise lock onto the newest EVR of the base `syslog-ng`
    # package currently in the repo. Pinning the entire subpackage set to a
    # single EVR is required because nightly builds occasionally don't
    # republish every subpackage in lock-step (e.g. when a subpackage is
    # added / removed / temporarily skipped). The strict
    # `Requires: syslog-ng(x86-64) = <EVR>` of any stale leftover would then
    # drag in a mismatched base package and make the transaction
    # unresolvable. Always pinning side-steps that entirely.
    if [ -n "${PACKAGE_VERSION:-}" ]; then \
        RESOLVED_VERSION="${PACKAGE_VERSION}"; \
        echo "Installing locked syslog-ng version: ${RESOLVED_VERSION}"; \
    else \
        RESOLVED_VERSION="$(dnf -q repoquery --repo="$OSE_REPO_ID" --latest-limit=1 \
            --queryformat='%{evr}\n' 'syslog-ng' | head -n1)"; \
        [ -n "$RESOLVED_VERSION" ] || { echo "ERROR: could not resolve newest syslog-ng EVR from OSE repo" >&2; exit 1; }; \
        echo "Installing newest syslog-ng version: ${RESOLVED_VERSION}"; \
    fi && \
    # Enumerate the base package + every syslog-ng-* subpackage that exists
    # at the resolved EVR. -devel / -debug* are excluded (build-time /
    # debugging artefacts, not runtime). The java subpackage is also
    # excluded to keep the image lean — pulling OpenJDK would roughly
    # double the image size. Subpackages that don't have a build at the
    # resolved EVR (e.g. ones intentionally dropped this round) are simply
    # not enumerated, which is the correct behaviour.
    SYSLOG_PKGS="$(dnf -q repoquery --repo="$OSE_REPO_ID" --queryformat='%{name} %{evr}\n' 'syslog-ng' 'syslog-ng-*' \
        | awk -v ver="$RESOLVED_VERSION" '$2 == ver { print $1 }' \
        | grep -Ev -- '-(devel|debuginfo|debugsource)$' \
        | grep -Ev '^syslog-ng-java$' \
        | sort -u)" && \
    if [ -z "$SYSLOG_PKGS" ]; then echo "ERROR: no syslog-ng packages found at EVR ${RESOLVED_VERSION} in OSE repo" >&2; exit 1; fi && \
    SYSLOG_PKGS="$(echo "$SYSLOG_PKGS" | sed "s/\$/-${RESOLVED_VERSION}/")" && \
    dnf -y install --setopt=install_weak_deps=False \
        $SYSLOG_PKGS jemalloc && \
    # dnf-plugins-core was only needed to flip CRB on; drop it again so it
    # doesn't bloat the runtime image. EPEL / CRB repo metadata is kept so
    # the user can still `dnf install` extras downstream.
    dnf -y remove dnf-plugins-core && \
    dnf clean all && \
    rm -rf /var/cache/dnf /var/cache/yum \
           /var/log/dnf* /var/log/hawkey.log \
           /tmp/* /var/tmp/*

#
# Preload jemalloc into the syslog-ng service via a systemd drop-in.
# The library path is resolved at build time so we fail early if it
# is missing from the image.
#
RUN JEMALLOC_LIB="$(rpm -ql jemalloc | grep -E '/libjemalloc\.so\.[0-9]+$' | head -n1)" && \
    [ -n "${JEMALLOC_LIB}" ] && \
    mkdir -p /etc/systemd/system/syslog-ng.service.d && \
    printf '[Service]\nEnvironment=LD_PRELOAD=%s\n' "${JEMALLOC_LIB}" \
        > /etc/systemd/system/syslog-ng.service.d/10-jemalloc.conf

#
# Enable the syslog-ng service so systemd starts it on boot.
#
RUN systemctl enable syslog-ng.service

COPY syslog-ng.conf /etc/syslog-ng/syslog-ng.conf

EXPOSE 514/udp
EXPOSE 601/tcp
EXPOSE 6514/tcp

HEALTHCHECK --interval=2m --timeout=5s --start-period=30s CMD /usr/sbin/syslog-ng-ctl healthcheck --timeout 5

# systemd stops cleanly on SIGRTMIN+3
STOPSIGNAL SIGRTMIN+3

VOLUME [ "/sys/fs/cgroup" ]

# Run systemd as PID 1. syslog-ng is started via its installed unit file.
# Note: the container must be run with a writable cgroup hierarchy and a
# tmpfs /run, e.g.:
#   docker run --privileged --cgroupns=host \
#       --tmpfs /run --tmpfs /run/lock \
#       -v /sys/fs/cgroup:/sys/fs/cgroup:rw ...
# On a plain Linux host with cgroup v2, `--privileged --cgroupns=host` is
# usually sufficient on its own; the explicit --tmpfs / cgroup mounts are
# required under Docker Desktop (macOS / Windows LinuxKit VM).
ENTRYPOINT ["/usr/sbin/init"]
