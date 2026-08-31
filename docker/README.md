# `balabit/syslog-ng` and `balabit/syslog-ng-rpm`
  * Syslog-ng is installed with all of its modules
  * Two image flavors are produced from this directory, each published to a dedicated Docker Hub repository:
    * `syslog-ng.deb.dockerfile` &mdash; Debian (`debian:trixie`) based, installs the DEB packages from the syslog-ng APT repository. syslog-ng runs in the foreground (`docker logs` shows the console output). Published to [`balabit/syslog-ng`](https://hub.docker.com/r/balabit/syslog-ng).
    * `syslog-ng.rpm.dockerfile` &mdash; AlmaLinux 9 based, installs the RPM packages from the syslog-ng DNF repository. The image ships with `systemd` as PID 1 and syslog-ng is managed as a systemd service. Only the runtime dependencies of the syslog-ng RPM (and its modules) are installed on top of the minimal AlmaLinux base &mdash; no extra build-time tooling is added. Published to [`balabit/syslog-ng-rpm`](https://hub.docker.com/r/balabit/syslog-ng-rpm).
  * Both flavors support `stable` and `nightly` packages, selected via the `PKG_TYPE` build arg.
  * You can use your own `syslog-ng.conf` or fall back to use the default one
  * Images are automatically rebuilt weekly with the latest security patches

Please check the syslog-ng image tags at the official docker repository: [https://hub.docker.com/r/balabit/syslog-ng](https://hub.docker.com/r/balabit/syslog-ng), or [https://hub.docker.com/r/balabit/syslog-ng-rpm](https://hub.docker.com/r/balabit/syslog-ng-rpm).

For information on how these images are built and published, see [PUBLISH-DOCKER-IMAGE.md](../.github/workflows/PUBLISH-DOCKER-IMAGE.md)

## Available Image Tags

- `latest` - Latest stable release with current security patches (rebuilt weekly)
- `X.Y.Z` - Specific version tags (e.g., `4.11.0`)
- `nightly` - Development builds with cutting-edge features (built nightly from develop branch)

## Building locally

The default Debian Trixie / DEB image:

```bash
docker build \
  -f docker/syslog-ng.deb.dockerfile \
  -t syslog-ng:debian docker/
```

The AlmaLinux 9 / RPM image (with embedded systemd):

```bash
docker build \
  --build-arg BASE_IMAGE=almalinux:9 \
  -f docker/syslog-ng.rpm.dockerfile \
  -t syslog-ng:alma9 docker/
```

Use `--build-arg PKG_TYPE=nightly` to pull from the nightly repository, or
`--build-arg PACKAGE_VERSION=4.11.0-1` to pin a specific package version
(the same build arg is consumed by both `syslog-ng.deb.dockerfile` and `syslog-ng.rpm.dockerfile`).

## Running the images

The "Running &hellip;" subsections below use the published image references
(`balabit/syslog-ng:latest` for DEB, `balabit/syslog-ng-rpm:latest` for
RPM). To run an image you built locally with the commands above, simply
substitute the local tag &mdash; all other flags stay the same:

| Flavor | Published image                | Locally built tag (from above) |
| ------ | ------------------------------ | ------------------------------ |
| DEB    | `balabit/syslog-ng:latest`     | `syslog-ng:debian`             |
| RPM    | `balabit/syslog-ng-rpm:latest` | `syslog-ng:alma9`              |

### Running the Debian / DEB image

The DEB image's `ENTRYPOINT` is a small wrapper script
(`/usr/local/bin/entrypoint.sh`) that runs syslog-ng in the foreground
(`/usr/sbin/syslog-ng -F`). Anything you pass after the image name is
forwarded to syslog-ng as additional command-line flags:

```bash
sudo docker run -it \
  -p 514:514/udp -p 601:601 -p 6514:6514 \
  --name syslog-ng balabit/syslog-ng:latest
```

Enable verbose/debug output by appending syslog-ng flags:

```bash
sudo docker run -it \
  -p 514:514/udp -p 601:601 -p 6514:6514 \
  --name syslog-ng balabit/syslog-ng:latest -edv
```

To run with a custom configuration, mount it over
`/etc/syslog-ng/syslog-ng.conf`:

```bash
sudo docker run -it \
  -v "$PWD/syslog-ng.conf":/etc/syslog-ng/syslog-ng.conf \
  -p 514:514/udp -p 601:601 -p 6514:6514 \
  --name syslog-ng balabit/syslog-ng:latest
```

### Running the AlmaLinux 9 / systemd image

Because the RPM image uses `systemd` as PID 1, it must be started with a
writable cgroup hierarchy and a tmpfs `/run`. On a plain Linux host with
cgroup v2, `--privileged --cgroupns=host` is usually enough; on Docker
Desktop (macOS / Windows LinuxKit VM) the cgroup and `/run` mounts must be
provided explicitly:

```bash
sudo docker run -d --privileged --cgroupns=host \
  --tmpfs /run --tmpfs /run/lock \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  -p 514:514/udp -p 601:601 -p 6514:6514 \
  --name syslog-ng balabit/syslog-ng-rpm:latest
```

For a less permissive setup (drop `--privileged`, keep only what systemd
actually needs):

```bash
sudo docker run -d \
  --cgroupns=host --cap-add SYS_ADMIN \
  --tmpfs /run --tmpfs /run/lock \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  -p 514:514/udp -p 601:601 -p 6514:6514 \
  --name syslog-ng balabit/syslog-ng-rpm:latest
```

If the container exits immediately with no logs, it's almost always the
cgroup / `/run` setup above &mdash; systemd routes its startup messages to the
journal, not the container's stdout, so `docker logs` will be empty. To
make systemd log to the console for debugging, add
`-e SYSTEMD_LOG_TARGET=console`.

syslog-ng itself is started by systemd via the installed `syslog-ng.service`
unit; you can interact with it the usual way:

```bash
sudo docker exec -it syslog-ng systemctl status syslog-ng
sudo docker exec -it syslog-ng journalctl -u syslog-ng -f
```

## Exposed Ports in the default configuration

The following ports are exposed:
 * Syslog UDP: 514,
 * Syslog TCP: 601,
 * Syslog TLS: 6514

Syslog-ng will listen on these ports and forwards the logs into the file
`/var/log/syslog`. You can check the default configuration in the source
repository of this image.

## Using default configuration
Assume that the following ports are not used on host machine, because they can conflict: `514`, `601`:

```bash
sudo docker run -it -p 514:514/udp -p 601:601 --name syslog-ng balabit/syslog-ng:latest
```
By default syslog-ng will not print any debug messages to the console. If you want to see more debug messages you need to start the containers in this way:

```bash
sudo docker run -it -p 514:514/udp -p 601:601 --name syslog-ng balabit/syslog-ng:latest -edv
```

## Using custom syslog-ng configuration
You can override the default configuration by mounting a configuration file under `/etc/syslog-ng/syslog-ng.conf`:

```bash
sudo docker run -it -v "$PWD/syslog-ng.conf":/etc/syslog-ng/syslog-ng.conf balabit/syslog-ng:latest
```

## Reading logs from other containers
An example is used to describe how syslog-ng can read logs from other containers.

Assume that you have already running an `apache2` container which exposes its logs as a mounted volume under "/var/log/apache2/". We will read the apache logs and send them to a remote host (`1.2.3.4:514`). The example syslog-ng configuration file is stored in the current directory as `syslog-ng.conf`.

```
source s_apache {
  file("/var/log/apache2/access.log");
};

destination d_remote {
  tcp("1.2.3.4" port(514));
};

log {
  source(s_apache);
  destination(d_remote);
};
```

Now we can start syslog-ng:

```bash
sudo docker run -it --volumes-from [containerID for apache2] -v "$PWD/syslog-ng.conf":/etc/syslog-ng/syslog-ng.conf balabit/syslog-ng:latest
```

## Entering into a container
Assume that your running container has a name "syslog-ng". In this case we can enter into this container by executing the following command:

```bash
sudo docker exec -it syslog-ng /bin/bash
```

## More information
For detailed information on how to run your central log server in Docker and other Docker-related syslog-ng use cases, see the blog post [Your central log server in Docker](https://syslog-ng.com/blog/central-log-server-docker/).


## FAQ

### capabilities

If the given configuration requires, syslog-ng tries to set some POSIX capabilities at startup, but (by default) Docker do not grant capabilities to the containers. Mainly there are three methods to circumvent this:
 * If you do not require any capability (i.e. don't want to listen on ports under 1024 - NET_BIND_SERVICE), simply start syslog-ng with the `--no-caps` option.
 * If you know precisely the type of capability you need, use the `--cap-add` option of the Docker service.
 * (For development/testing purpose only!) To grant ALL of the capabilities to your container, start it with the `privileged` option. However, we do not recommend this method in production environments.

