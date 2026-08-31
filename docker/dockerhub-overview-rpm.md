# syslog-ng (AlmaLinux 9 / RPM, systemd-managed)

Official RPM-flavored Docker image of [syslog-ng OSE](https://github.com/syslog-ng/syslog-ng), built on top of `almalinux:9` and running `syslog-ng` as a regular `systemd` service.

For the Debian-based image (entrypoint-style, `syslog-ng -F` as PID 1), see [`balabit/syslog-ng`](https://hub.docker.com/r/balabit/syslog-ng).

## What's in the image

- AlmaLinux 9 base, kept up-to-date with the latest base-image security patches on every weekly rebuild.
- `syslog-ng` and **every published `syslog-ng-*` module subpackage** from the official syslog-ng OSE DNF repository. Java-based modules (`syslog-ng-java`) are intentionally excluded to keep the image lean.
- `jemalloc` preloaded into the `syslog-ng.service` via a systemd drop-in for better allocator behaviour under sustained load.
- `systemd` as PID 1 — `syslog-ng.service` is enabled and started automatically on container boot.

## Available tags

| Tag | Description |
|---|---|
| `latest` | Latest official stable release |
| `nightly` | Latest developer nightly build from the `develop` branch |
| `<version>` (e.g. `4.11.0`) | Specific syslog-ng release |

Multi-arch: `linux/amd64`, `linux/arm64`.

## Quick start

Because `systemd` runs as PID 1, the container needs a writable cgroup hierarchy and a tmpfs `/run`. The exact invocation depends on the host.

### Linux host (cgroup v2 — most modern distros)

```shell
docker run -d --name syslog-ng-rpm \
    --privileged --cgroupns=host \
    -p 514:514/udp -p 601:601/tcp -p 6514:6514/tcp \
    balabit/syslog-ng-rpm:latest
```

### Docker Desktop (macOS / Windows)

Docker Desktop's LinuxKit VM requires explicit tmpfs and cgroup mounts:

```shell
docker run -d --name syslog-ng-rpm \
    --privileged --cgroupns=host \
    --tmpfs /run --tmpfs /run/lock \
    -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    -e SYSTEMD_LOG_TARGET=console \
    -p 514:514/udp -p 601:601/tcp -p 6514:6514/tcp \
    balabit/syslog-ng-rpm:latest
```

`SYSTEMD_LOG_TARGET=console` is optional — it routes `systemd`'s own boot messages to container stdout for easier debugging.

## Inspecting and controlling syslog-ng

`syslog-ng` runs as a systemd unit, so the usual `systemctl` and `journalctl` commands apply inside the container:

```shell
docker exec -it syslog-ng-rpm systemctl status syslog-ng
docker exec -it syslog-ng-rpm journalctl -u syslog-ng -e
docker exec -it syslog-ng-rpm syslog-ng-ctl stats
docker exec -it syslog-ng-rpm syslog-ng-ctl healthcheck
```

> **Note:** `systemd` logs to the journal, **not** to container stdout. `docker logs` will normally be empty — use `journalctl -u syslog-ng` (or set `-e SYSTEMD_LOG_TARGET=console` as shown above) to see syslog-ng's startup output.

## Configuration

The image ships a minimal default [`/etc/syslog-ng/syslog-ng.conf`](https://github.com/syslog-ng/syslog-ng/blob/develop/docker/syslog-ng.conf) which writes the collected logs to `/var/log/messages` and `/var/log/messages-kv.log` inside the container. To use your own configuration:

```shell
docker run -d --name syslog-ng-rpm \
    --privileged --cgroupns=host \
    --tmpfs /run --tmpfs /run/lock \
    -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    -v /path/to/your/syslog-ng.conf:/etc/syslog-ng/syslog-ng.conf:ro \
    -p 514:514/udp -p 601:601/tcp -p 6514:6514/tcp \
    balabit/syslog-ng-rpm:latest
```

To persist the log output, mount a host directory at whatever path your `file()` (or other) destinations write to, for example `-v /path/to/host/logs:/var/log/syslog-ng` and point your config's `file("/var/log/syslog-ng/...")` destinations at it.

After editing the mounted config, reload syslog-ng without restarting the container:

```shell
docker exec syslog-ng-rpm systemctl reload syslog-ng
```

## Exposed ports

| Port | Protocol | Purpose |
|---|---|---|
| `514`  | UDP | RFC3164 / RFC5424 syslog |
| `601`  | TCP | RFC5424 syslog over TCP |
| `6514` | TCP | RFC5424 syslog over TLS |

> **Note on TLS:** the default config does not ship a key/cert pair, so with the stock configuration port `6514` is exposed but the TLS listener is inactive (syslog-ng will log a startup warning). Mount your own config with a `tls(key-file(...) cert-file(...))` block on the network source to enable it.

## Healthcheck

The image registers a Docker healthcheck that calls `syslog-ng-ctl healthcheck` every two minutes, so orchestrators can rely on `docker inspect` / `docker ps` to detect a stuck syslog-ng.

## Stopping the container

`systemd` stops cleanly on `SIGRTMIN+3` (already set via `STOPSIGNAL` in the image), so plain `docker stop syslog-ng-rpm` will gracefully shut the service down.

## Debugging

For an interactive shell inside a running container:

```shell
docker exec -it syslog-ng-rpm /bin/bash
```

For verbose `systemd` boot output, add `-e SYSTEMD_LOG_TARGET=console` to the `docker run` command (see the Docker Desktop example above).

For syslog-ng's own debug output you have two options:

1. **Run syslog-ng in the foreground after stopping the service.** A second instance cannot coexist with the already-running unit, so the unit must be stopped first:

   ```shell
   docker exec -it syslog-ng-rpm bash -c \
       'systemctl stop syslog-ng && /usr/sbin/syslog-ng -Fedv'
   ```

2. **Override `ExecStart=` via a systemd drop-in** (persistent, restart-clean). Inside the container:

   ```shell
   # Capture the current ExecStart line so we don't drift from the unit shipped by the RPM:
   ORIG_EXEC=$(systemctl cat syslog-ng | awk -F= '/^ExecStart=/ { sub(/^ExecStart=/, ""); print; exit }')
   mkdir -p /etc/systemd/system/syslog-ng.service.d
   cat > /etc/systemd/system/syslog-ng.service.d/20-debug.conf <<EOF
   [Service]
   ExecStart=
   ExecStart=${ORIG_EXEC} -edv
   EOF
   systemctl daemon-reload
   systemctl restart syslog-ng
   journalctl -u syslog-ng -f
   ```

   The empty `ExecStart=` line is required by systemd to clear the original before re-defining it.

## FAQ — Linux capabilities

This image starts as `--privileged` because `systemd` needs it. If you adapt the run command to a less-privileged setup (for example by dropping `--privileged` and granting only what `systemd` strictly requires), syslog-ng's own capability management may still fail with messages like *"Error managing capability set"*. The same workarounds as the Debian image apply — disable capability management inside syslog-ng by editing the unit's `ExecStart=` to append `--no-caps`, or grant only `CAP_NET_BIND_SERVICE` and `CAP_SYSLOG` to the container.

## Source and support

- **Source / Dockerfile:** <https://github.com/syslog-ng/syslog-ng/blob/develop/docker/syslog-ng.rpm.dockerfile>
- **Build & run guide:** <https://github.com/syslog-ng/syslog-ng/blob/develop/docker/README.md>
- **syslog-ng documentation:** <https://syslog-ng.github.io>
- **Issues / discussions:** <https://github.com/syslog-ng/syslog-ng>
