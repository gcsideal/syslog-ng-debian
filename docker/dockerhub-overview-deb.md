# syslog-ng (Debian, entrypoint-managed)

Official Debian-based Docker image of [syslog-ng OSE](https://github.com/syslog-ng/syslog-ng), built on top of `debian:trixie` and running `syslog-ng` directly as PID 1 via a thin entrypoint wrapper.

For the systemd-managed RPM variant (AlmaLinux 9), see [`balabit/syslog-ng-rpm`](https://hub.docker.com/r/balabit/syslog-ng-rpm).

## What's in the image

- Debian (trixie) base, kept up-to-date with the latest base-image security patches on every weekly rebuild.
- `syslog-ng` and **every published `syslog-ng-mod-*` package** from the official syslog-ng OSE APT repository. Java-based modules (`syslog-ng-mod-java`, `syslog-ng-mod-java-common-lib`, `syslog-ng-mod-hdfs`) are intentionally excluded to keep the image lean.
- `libjemalloc2` preloaded into syslog-ng via the entrypoint wrapper for better allocator behaviour under sustained load.
- `syslog-ng -F` is PID 1 — no `systemd`, no cgroup gymnastics, plain `docker run` is enough.

## Available tags

| Tag | Description |
|---|---|
| `latest` | Latest official stable release |
| `nightly` | Latest developer nightly build from the `develop` branch |
| `<version>` (e.g. `4.11.0`) | Specific syslog-ng release |

Multi-arch: `linux/amd64`, `linux/arm64`.

## Quick start

```shell
docker run -d --name syslog-ng \
    -p 514:514/udp -p 601:601/tcp -p 6514:6514/tcp \
    balabit/syslog-ng:latest
```

## Inspecting and controlling syslog-ng

`syslog-ng` logs directly to container stdout, so `docker logs` works as expected:

```shell
docker logs -f syslog-ng
docker exec -it syslog-ng syslog-ng-ctl stats
docker exec -it syslog-ng syslog-ng-ctl healthcheck
```

## Configuration

The image ships a minimal default [`/etc/syslog-ng/syslog-ng.conf`](https://github.com/syslog-ng/syslog-ng/blob/develop/docker/syslog-ng.conf) which writes the collected logs to `/var/log/messages` and `/var/log/messages-kv.log` inside the container. To use your own configuration:

```shell
docker run -d --name syslog-ng \
    -v /path/to/your/syslog-ng.conf:/etc/syslog-ng/syslog-ng.conf:ro \
    -p 514:514/udp -p 601:601/tcp -p 6514:6514/tcp \
    balabit/syslog-ng:latest
```

To persist the log output, mount a host directory at whatever path your `file()` (or other) destinations write to, for example:

```shell
    -v /path/to/host/logs:/var/log/syslog-ng
```

(and point your config's `file("/var/log/syslog-ng/...")` destinations at it).

After editing the mounted config, reload syslog-ng without restarting the container:

```shell
docker exec syslog-ng syslog-ng-ctl reload
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

## Debugging

To get verbose startup output, override the command and pass syslog-ng's own debug flags:

```shell
docker run --rm -it --name syslog-ng \
    -p 514:514/udp -p 601:601/tcp \
    balabit/syslog-ng:latest -edv
```

To get an interactive shell inside a running container:

```shell
docker exec -it syslog-ng /bin/bash
```

## Reading logs from other containers

You can use this image as a central log collector for sibling containers via `--volumes-from`. Point the app container's log directory at a shared volume, then mount that volume into the syslog-ng container and add a `file()` (or `wildcard-file()`) source for it. Example sketch:

```shell
docker run -d --name app -v /var/log/app debian:trixie ...
docker run -d --name syslog-ng --volumes-from app \
    -v /path/to/syslog-ng.conf:/etc/syslog-ng/syslog-ng.conf:ro \
    -p 514:514/udp -p 601:601/tcp \
    balabit/syslog-ng:latest
```

A matching `syslog-ng.conf` would declare a `file("/var/log/app/...")` (or `wildcard-file()`) source and forward it to whichever destinations you need. See the syslog-ng documentation for the current configuration syntax.

## FAQ — Linux capabilities

By default, syslog-ng tries to manage Linux capabilities (for example to drop `CAP_NET_BIND_SERVICE` after binding port `514`). Inside an unprivileged container this can fail with messages like *"Error managing capability set"*. Three common workarounds:

- **Disable capability management inside syslog-ng** by appending `--no-caps` to the command:

  ```shell
  docker run -d --name syslog-ng -p 514:514/udp balabit/syslog-ng:latest --no-caps
  ```

- **Grant only the capabilities syslog-ng actually needs** (preferred for production):

  ```shell
  docker run -d --name syslog-ng \
      --cap-add NET_BIND_SERVICE --cap-add SYSLOG \
      -p 514:514/udp balabit/syslog-ng:latest
  ```

- **Run privileged** (simple but broad — avoid in production):

  ```shell
  docker run -d --name syslog-ng --privileged -p 514:514/udp balabit/syslog-ng:latest
  ```

## Source and support

- **Source / Dockerfile:** <https://github.com/syslog-ng/syslog-ng/blob/develop/docker/syslog-ng.deb.dockerfile>
- **Build & run guide:** <https://github.com/syslog-ng/syslog-ng/blob/develop/docker/README.md>
- **syslog-ng documentation:** <https://syslog-ng.github.io>
- **Issues / discussions:** <https://github.com/syslog-ng/syslog-ng>
