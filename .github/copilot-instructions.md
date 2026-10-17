# Repository instructions

## Build, test, and lint

This repository focuses on Debian packaging of syslog-ng (debian//*). The primary packaging workflow uses git-buildpackage (gbp) and Debian packaging tools rather than developing the upstream tree in-place.

Build the Debian packages (git-buildpackage required):

```sh
# ensure git-buildpackage (gbp) is installed
# from the repository root (a clean, committed branch):
gbp buildpackage -us -uc
```

This produces source/binary packages and the .changes/.deb artifacts. The Debian rules in `debian/rules` are configured to build in a separate build tree (see `override_dh_auto_configure`); local builds commonly use `debian/build-tree`.

To run autopkgtest on the built package (autopkgtest must be installed and set up on your host):

```sh
# Example: run autopkgtest on the generated .changes file
autopkgtest ./debian/syslog-ng_*.changes
```

Autopkgtest requires a prepared test environment (LXC, schroot, or a local harness) and may need additional setup. Test definitions and helper scripts live under `debian/tests` and the `tests/light` test-suite; review those before running tests.

For building inside the project-provided docker-based build system (dbld) — useful for producing distribution artifacts reproducibly — see `dbld/README.md` and use targets such as:

```sh
./dbld/rules shell-devshell   # enter a containerized development shell
./dbld/rules deb-ubuntu-jammy # build distro-specific packages
```

Formatting and lint checks still apply to packaging and upstream code:

```sh
make style-check    # C source formatting
make light-linters  # Python test linters (from build dir)
```

If you need to execute a single light functional test directly (useful for debugging the test code itself), the pytest invocation below still applies (requires a built and installed syslog-ng and a Python venv):

```sh
cd tests/light
/path/to/build/venv/bin/pytest -v --installdir=/path/to/install \
  functional_tests/path/to/test_file.py::test_function_name
```

For more packaging details, inspect `debian/rules`, `debian/control`, and `debian/patches/`.

## Modifying syslog-ng code

This is a Debian packaging repository, so changes to upstream syslog-ng source must be carried as quilt patches in `debian/patches/`, not committed as direct edits to the upstream source tree. Use `gbp pq` to manage those patches:

```sh
# From the packaging branch, with a clean worktree:
gbp pq import
# Edit upstream source and tests on the patch-queue branch, then commit the changes:
git add path/to/changed/files
git commit
# Export the patch-queue commits to debian/patches/ and update debian/patches/series:
gbp pq export
```

Keep each commit focused on a coherent upstream change. After exporting, review the generated patch files and `debian/patches/series`, then build the Debian package and run the relevant autopkgtests. Changes to Debian packaging itself (for example, `debian/rules` or package metadata) belong directly in `debian/`, not in an upstream patch. See `gbp pq --help` for options and branch handling.

## Architecture

- The Debian packaging in `debian/` builds upstream syslog-ng and defines the binary packages, install contents, maintainer scripts, and package tests. Debian-specific source modifications are applied as quilt patches listed in `debian/patches/series`.
- In the upstream source carried by this repository, `syslog-ng/` contains the daemon entry point; `lib/` implements shared runtime and configuration machinery. The core includes configuration lexing/parsing (`lib/cfg-lex.l`, `lib/cfg-grammar.y`), log messages and pipeline primitives, transports, filters, parsers, rewrites, templates, queues, and scheduling.
- `modules/` contains loadable functionality such as source and destination drivers, parsers, and template functions. Modules register plugins with the core and may be enabled or omitted depending on configure options and available dependencies. Configuration grammars in module directories define their configuration syntax.
- `scl/` provides reusable syslog-ng configuration snippets and libraries. `doc/` contains project documentation and manpages; `debian/` contains Debian packaging, while `dbld/` supplies container-based build and package targets.
- Tests live alongside the relevant core library or module for C unit tests; `tests/light/functional_tests/` contains Python integration tests that exercise a built and installed daemon.

## Repository-specific conventions

- Finish repository changes by creating a git commit; include the relevant summary and Debian bug references in the commit message, and let `gbp dch` update `debian/changelog`.
- Follow the existing GNU-like C style and `.astylerc`; use `make style-check` to check formatting. Python light-test formatting and linting are enforced by the configuration in `tests/light/.pre-commit-config.yaml`.
- Add release notes under `news/` using `<type>-<PR_ID>.md` (`feature`, `bugfix`, `packaging`, `developer-note`, or `other`). Keep entries brief, start with the affected module, and follow `news/README.md`.
- Commit subjects use `module: short description`; the module identifies the affected area (for example, `python`, `redis`, or `persist`). See `CONTRIBUTING.md` for the required commit format and sign-off details.
- In light functional tests, prefer the Config API helpers when available and do not mix them with raw configuration. Use `freq=0` for immediate example-generator output, insert a syslog parser before facility/level filters, and use `read_logs(n)` when checking multiple messages.
