# syslog-ng Light Test Framework Guide

## Purpose

This guide provides patterns and rules for writing syslog-ng functional tests using the light test framework.

**Target Audience:** Developers and AI agents writing or maintaining syslog-ng tests.

---

## Quick Reference

### Decision Tree: Which Source to Use?

```text

Are you testing SOURCE DRIVER behavior?
├─ YES → Use that source driver (file/network/syslog)
└─ NO  → Use example-msg-generator (faster, simpler)

Are you testing LOGPATH FLAGS (final/fallback/catch-all)?
├─ YES → Use file source (flags need persistent input)
└─ NO  → Use example-msg-generator

Are you testing NETWORK FEATURES (TCP/TLS/proxy-protocol)?
├─ YES → Use network/syslog source
└─ NO  → Use example-msg-generator

```

### Decision Tree: Config API vs Raw Config?

```text

Does the feature have config.create_*() helper?
├─ YES → Use Config API (preferred)
│        Examples: most sources, destinations, parsers, filters
└─ NO  → Use Raw Config
         Examples: map-value-pairs, wildcard-file, complex nested logs

```

### Critical Rules

1. ✅ **Use `freq=0`** in example-msg-generator (immediate generation)
2. ✅ **Add syslog-parser** before facility/level filters
3. ✅ **Use unique persist-name** for shared destinations
4. ✅ **Use `read_logs(n)`** for multiple messages (not `read_log()`)
5. ❌ **NEVER mix** Config API with Raw Config (causes KeyError)

---

## Table of Contents

1. [Quick Start](#quick-start) - Write your first test in 5 minutes
2. [Source Selection](#source-selection) - Which source to use when
3. [Configuration Patterns](#configuration-patterns) - Config API vs Raw Config
4. [Common Patterns](#common-patterns) - Code templates and examples
5. [Common Pitfalls](#common-pitfalls) - Avoid these mistakes
6. [Clean Code Guidelines](#clean-code-guidelines) - Write maintainable tests
7. [Test Organization](#test-organization) - Directory structure and build files
8. [Running and Validation](#running-and-validation) - Execute and debug tests
9. [Multiplatform Compatibility](#multiplatform-compatibility) - macOS, FreeBSD, Linux
10. [Checklist for New Tests](#checklist-for-new-tests) - Pre-submit checklist
11. [Reference](#reference) - Detailed technical information

---

## Quick Start

### Minimal Test Template

```python

#!/usr/bin/env python
#############################################################################
# Copyright (c) 2026 OneIdentity
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 as published
# by the Free Software Foundation, or (at your option) any later version.
#############################################################################

# Test basic message generation and filtering.
#
def test_example(config, syslog_ng):
    """Test example message generation."""

    # 1. Create source (generates messages)
    source = config.create_example_msg_generator_source(
        num=10,
        freq=0,  # Generate immediately
        template=config.stringify("<41>Feb 11 10:00:00 host test: message"),
    )

    # 2. Create destination (writes to file)
    dest = config.create_file_destination(file_name="output.log")

    # 3. Create logpath (connect source to destination)
    config.create_logpath(statements=[source, dest])

    # 4. Start syslog-ng
    syslog_ng.start(config)

    # 5. Validate output
    assert "message" in dest.read_log()

```

**That's it!** This is a complete, runnable test.

### Adding Filters and Parsers

```python

def test_with_filter(config, syslog_ng):
    """Test syslog parser and facility filter."""

    source = config.create_example_msg_generator_source(
        num=5,
        freq=0,
        template=config.stringify("<41>message"),  # priority 41 = syslog facility
    )

    # Parse syslog priority to extract facility/level
    parser = config.create_syslog_parser()

    # Filter messages by facility
    filter_syslog = config.create_filter("facility(syslog)")

    dest = config.create_file_destination(file_name="filtered.log")

    # Order matters: source → parser → filter → destination
    config.create_logpath(statements=[source, parser, filter_syslog, dest])

    syslog_ng.start(config)

    logs = dest.read_logs(5)
    assert len(logs) == 5

```

---

## Source Selection

### Use `example-msg-generator` by Default

**When to use:**
- ✅ Parser tests (csv, regexp, app-parser, db-parser)
- ✅ Filter tests (facility, level, custom filters)
- ✅ Rewrite tests (set-tag, set-pri, cc-mask)
- ✅ Template function tests
- ✅ Most destination tests

**Why:**
- Faster (no file I/O or network setup)
- Simpler (no external dependencies)
- Deterministic (exact message count)

**Example:**

```python

source = config.create_example_msg_generator_source(
    num=100,
    freq=0,  # CRITICAL: Generate immediately, not over time
    template=config.stringify("<41>Feb 11 10:00:00 host prog: test message"),
)

```

### Use `file` Source for File-Specific Tests

**When to use:**
- ✅ Testing file source behavior (wildcards, exclusions, rotation)
- ✅ Testing logpath flags (final/fallback/catch-all need persistent input)
- ✅ Multi-line parsing (group-lines parser)
- ✅ Config reload scenarios with persistent input

**Pattern:**

```python

def test_file_source(config, syslog_ng):
    """Test wildcard file source."""

    # 1. Create files BEFORE starting syslog-ng
    os.makedirs("input", exist_ok=True)
    for i in range(3):
        with open(f"input/file{i}.log", 'a') as f:
            f.write("test message\n")

    # 2. Use raw config (wildcard-file has no Config API helper)
    raw_config = f"""
@version: {config.get_version()}
source s {{ wildcard-file(base-dir("input") filename-pattern("*.log")); }};
destination d {{ file("output.log"); }};
log {{ source(s); destination(d); }};
"""

    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # 3. Validate
    import time
    time.sleep(2)  # Wait for file processing
    assert os.path.exists("output.log")

```

### Use `network`/`syslog` Source for Network Tests

**When to use:**
- ✅ Testing network source behavior
- ✅ Testing protocols (TCP, UDP, TLS, proxy-protocol)
- ✅ Testing network-specific features (reconnect, burst traffic)

**Example:**

```python

source = config.create_network_source(
    ip="localhost",
    port=port_allocator(),
    transport="tcp",
)

```

---

## Configuration Patterns

### Pattern 1: Config API (Preferred)

**Use when:** Feature has `config.create_*()` helper

**Available Helpers:**
- `config.create_example_msg_generator_source()`
- `config.create_file_source()`
- `config.create_network_source()`
- `config.create_syslog_source()`
- `config.create_internal_source()`
- `config.create_file_destination()`
- `config.create_filter()`
- `config.create_syslog_parser()`
- Many others...

**Example:**

```python

def test_with_config_api(config, syslog_ng):
    """Modern test using Config API."""

    source = config.create_example_msg_generator_source(num=5, freq=0)
    parser = config.create_syslog_parser()
    filter_obj = config.create_filter("facility(syslog)")
    dest = config.create_file_destination(file_name="output.log")

    config.create_logpath(statements=[source, parser, filter_obj, dest])

    syslog_ng.start(config)
    assert len(dest.read_logs(5)) == 5

```

### Pattern 2: Raw Config (When Necessary)

**Use when:** Feature lacks Config API helper

**Features requiring Raw Config:**
- `map-value-pairs` parser
- `wildcard-file` source
- Complex nested log statements
- Custom grammar features

**Example:**

```python

def test_with_raw_config(config, syslog_ng):
    """Test map-value-pairs parser using raw config."""

    raw_config = f"""
@version: {config.get_version()}

source s_gen {{
    example-msg-generator(num(5) freq(0) template("test"));
}};

parser p_map {{
    map-value-pairs(key("MSG*" rekey(add-prefix("foo."))));
}};

destination d_file {{
    file("output.log" template("${{foo.MSG}}\\n"));
}};

log {{ source(s_gen); parser(p_map); destination(d_file); }};
"""

    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Read file directly (relative to current working directory)
    import time
    time.sleep(1)
    with open("output.log", 'r') as f:
        logs = f.readlines()
    assert len(logs) == 5

```

### ❌ NEVER Mix Config API with Raw Config

**Problem:** Mixing causes `KeyError: 'processed'` when accessing destination stats.

**Wrong:**

```python

dest = config.create_file_destination(file_name="output.log")
config.set_raw_config("source s { ... };")  # BREAKS dest.get_stats()!

```

**Correct:** Use one or the other, never both.

---

## Common Patterns

### Pattern: Multiple Messages with Validation

```python

NUM_MESSAGES = 100

def test_multiple_messages(config, syslog_ng):
    """Test processing multiple messages."""

    source = config.create_example_msg_generator_source(
        num=NUM_MESSAGES,
        freq=0,
        template=config.stringify("<41>test message"),
    )

    dest = config.create_file_destination(file_name="output.log")
    config.create_logpath(statements=[source, dest])

    syslog_ng.start(config)

    # Read multiple messages
    logs = dest.read_logs(NUM_MESSAGES)  # NOT read_log() - that reads only 1
    assert len(logs) == NUM_MESSAGES

```

### Pattern: Facility/Level Filtering

```python

PRI_SYSLOG_ALERT = 41  # facility=5 (syslog) * 8 + level=1 (alert)

def test_facility_filter(config, syslog_ng):
    """Test facility filtering."""

    source = config.create_example_msg_generator_source(
        num=10,
        freq=0,
        template=config.stringify(f"<{PRI_SYSLOG_ALERT}>message"),
    )

    # CRITICAL: Add syslog-parser before facility filter
    parser = config.create_syslog_parser()
    filter_obj = config.create_filter("facility(syslog)")

    dest = config.create_file_destination(file_name="output.log")

    config.create_logpath(statements=[source, parser, filter_obj, dest])

    syslog_ng.start(config)
    assert len(dest.read_logs(10)) == 10

```

### Pattern: Multiple Logpaths to Same File

```python

def test_shared_destination(config, syslog_ng):
    """Test multiple logpaths writing to same file."""

    source1 = config.create_example_msg_generator_source(num=5, freq=0)
    source2 = config.create_example_msg_generator_source(num=5, freq=0)

    # CRITICAL: Use unique persist-name for each destination
    dest1 = config.create_file_destination(
        file_name="output.log",
        persist_name="dest1",
    )
    dest2 = config.create_file_destination(
        file_name="output.log",
        persist_name="dest2",
    )

    config.create_logpath(statements=[source1, dest1])
    config.create_logpath(statements=[source2, dest2])

    syslog_ng.start(config)

    # Both destinations write to same file
    logs = dest1.read_logs(10)  # Reads all messages from file
    assert len(logs) == 10

```

### Pattern: Config Template Function

```python

def create_config_template(version, port, num_messages=10):
    """Generate configuration with parameters."""
    return f"""
@version: {version}

source s_tcp {{
    tcp(port({port}));
}};

destination d_file {{
    file("output.log");
}};

log {{
    source(s_tcp);
    destination(d_file);
}};
"""

def test_with_template(config, syslog_ng, port_allocator):
    """Test using config template."""

    port = port_allocator()
    raw_config = create_config_template(
        version=config.get_version(),
        port=port,
        num_messages=20,
    )

    config.set_raw_config(raw_config)
    syslog_ng.start(config)
    # ... rest of test

```

---

## Common Pitfalls

### 1. Missing `freq=0` in example-msg-generator

**Problem:** Messages generate slowly over time instead of immediately.

**❌ Wrong:**

```python

source = config.create_example_msg_generator_source(
    num=100,
    template=config.stringify("message"),
)
# Test may timeout waiting for messages!

```

**✅ Correct:**

```python

source = config.create_example_msg_generator_source(
    num=100,
    freq=0,  # Generate immediately
    template=config.stringify("message"),
)

```

### 2. Missing Syslog Parser Before Facility/Level Filter

**Problem:** Facility/level filters require parsed priority field.

**❌ Wrong:**

```python

config.create_logpath(statements=[
    source,
    config.create_filter("facility(syslog)"),  # Won't match anything!
    dest,
])

```

**✅ Correct:**

```python

config.create_logpath(statements=[
    source,
    config.create_syslog_parser(),  # Extracts facility/level from priority
    config.create_filter("facility(syslog)"),
    dest,
])

```

### 3. Using `read_log()` Instead of `read_logs(n)`

**Problem:** `read_log()` reads only 1 message.

**❌ Wrong:**

```python

logs = dest.read_log()  # Returns single string
assert len(logs) == 10  # Will fail! logs is a string, not a list

```

**✅ Correct:**

```python

logs = dest.read_logs(10)  # Returns list of 10 strings
assert len(logs) == 10

```

### 4. Mixing Config API with Raw Config

**Problem:** Causes `KeyError: 'processed'` when accessing destination stats.

**❌ Wrong:**

```python

dest = config.create_file_destination(file_name="output.log")
config.set_raw_config("source s { ... }; destination d { ... };")
dest.get_stats()  # KeyError: 'processed'

```

**✅ Correct:**

```python

# Option 1: Pure Config API
dest = config.create_file_destination(file_name="output.log")
config.create_logpath(statements=[source, dest])

# Option 2: Pure Raw Config
raw_config = "..."
config.set_raw_config(raw_config)
# Read file directly, don't use dest.get_stats()

```

### 5. Missing Unique persist-name for Shared Destinations

**Problem:** Multiple logpaths writing to same file cause persist-name collision.

**❌ Wrong:**

```python

dest = config.create_file_destination(file_name="output.log")
config.create_logpath(statements=[source1, dest])
config.create_logpath(statements=[source2, dest])
# Error: persist-name collision!

```

**✅ Correct:**

```python

dest1 = config.create_file_destination(
    file_name="output.log",
    persist_name="dest1",
)
dest2 = config.create_file_destination(
    file_name="output.log",
    persist_name="dest2",
)
config.create_logpath(statements=[source1, dest1])
config.create_logpath(statements=[source2, dest2])

```

---

## Clean Code Guidelines

### Rule 1: No Magic Numbers

**❌ Bad:**

```python

source = config.create_example_msg_generator_source(num=100, freq=0)
time.sleep(4)
assert "<41>" in logs

```

**✅ Good:**

```python

NUM_MESSAGES = 100
SETTLE_TIME = 4
PRI_SYSLOG_ALERT = 41  # facility=5 (syslog) * 8 + level=1 (alert)

source = config.create_example_msg_generator_source(num=NUM_MESSAGES, freq=0)
time.sleep(SETTLE_TIME)
assert f"<{PRI_SYSLOG_ALERT}>" in logs

```

### Rule 2: Extract Helper Functions

**❌ Bad - Repeated code:**

```python

def test_one(config, syslog_ng):
    with open("output.log", 'r') as f:
        lines = f.readlines()
    assert len(lines) == 10
    for msg in expected:
        assert any(msg in line for line in lines)

def test_two(config, syslog_ng):
    with open("output.log", 'r') as f:  # Duplicated!
        lines = f.readlines()
    assert len(lines) == 20
    for msg in expected:
        assert any(msg in line for line in lines)  # Duplicated!

```

**✅ Good - Helper function:**

```python

def validate_file_output(filename, expected_messages):
    """Validate file contains expected messages."""
    with open(filename, 'r') as f:
        lines = f.readlines()
    assert len(lines) == len(expected_messages)
    for msg in set(expected_messages):
        assert any(msg in line for line in lines), f"Missing: {msg}"

def test_one(config, syslog_ng):
    # ... test code ...
    validate_file_output("output.log", expected)

def test_two(config, syslog_ng):
    # ... test code ...
    validate_file_output("output.log", expected)

```

### Rule 3: Use Config Template Functions

**❌ Bad - Repeated config:**

```python

def test_one(config, syslog_ng):
    raw_config = f"""
@version: {config.get_version()}
source s {{ ... }};
destination d {{ ... }};
log {{ source(s); destination(d); }};
"""
    config.set_raw_config(raw_config)

def test_two(config, syslog_ng):
    raw_config = f"""  # Same config repeated!
@version: {config.get_version()}
source s {{ ... }};
destination d {{ ... }};
log {{ source(s); destination(d); }};
"""
    config.set_raw_config(raw_config)

```

**✅ Good - Template function:**

```python

def create_config(version, **params):
    """Generate config with parameters."""
    return f"""
@version: {version}
source s {{ ... }};
destination d {{ ... }};
log {{ source(s); destination(d); }};
"""

def test_one(config, syslog_ng):
    config.set_raw_config(create_config(config.get_version()))

def test_two(config, syslog_ng):
    config.set_raw_config(create_config(config.get_version()))

```

### Rule 4: Keep Test Functions Focused

**Target:** Under 20 lines per test function (excluding helpers)

**Structure:**

```python

# Test description in comments (not docstring for compatibility)
#
def test_example(config, syslog_ng):
    """Brief docstring."""

    # 1. Setup (create test data if needed)
    expected = create_test_data()

    # 2. Configure
    config.create_logpath(statements=[source, dest])

    # 3. Execute
    syslog_ng.start(config)

    # 4. Validate
    validate_output(dest, expected)

```

---

## Test Organization

### Directory Structure

```text

tests/light/functional_tests/
├── config_change/           # Config reload and change tests
├── destination_drivers/     # Destination-specific tests
│   ├── file_destination/
│   ├── network_destination/
│   ├── sql_destination/
│   └── unix_stream_destination/
├── filters/                 # Filter tests
├── logpath/                 # Logpath and flag tests
├── parsers/                 # Parser tests
│   ├── csv-parser/
│   ├── map-value-pairs/
│   └── regexp-parser/
├── performance/             # Performance/load tests
├── rewrites/                # Rewrite tests
├── source_drivers/          # Source-specific tests
│   ├── file_source/
│   ├── network_source/
│   └── syslog_source/
├── template_functions/      # Template function tests
└── templates/               # Template statement tests

```

**Rule:** Each feature gets its own subdirectory under the appropriate category.

### Build Files

#### Tests Run Automatically

**pytest auto-discovers** all `test_*.py` files - no registration needed.

**Do NOT modify** when adding tests:
- `tests/light/CMakeLists.txt`
- `tests/light/Makefile.am`

#### Distribution Packaging (Optional)

**Only update** `tests/light/functional_tests/Makefile.am` to include tests in release tarballs:

```makefile

EXTRA_DIST += \
	tests/light/functional_tests/filters/test_facility_and_level_filters.py \
	tests/light/functional_tests/parsers/csv-parser/test_csv_parser.py \
	tests/light/functional_tests/source_drivers/file_source/test_file_source.py \
	...

```

**Format:**
- One file per line
- End with ` \` (space + backslash) except last line
- Alphabetical order
- Tabs for indentation

---

## Running and Validation

### Run Tests

**Single file:**

```bash

cd /path/to/syslog-ng/tests/light
/path/to/build/venv/bin/pytest -v \
    --installdir=/path/to/build/install \
    functional_tests/path/to/test_file.py

```

**Single function:**

```bash

pytest -v --installdir=/path/to/install \
    functional_tests/test_file.py::test_function_name

```

**All tests:**

```bash

cd /path/to/build
make light-check

```

### Style Validation

**Run before pushing:**

```bash

cd /path/to/build
make light-linters

```

**Pre-commit hooks enforce:**
1. No trailing whitespace
2. Newline at end of file
3. flake8 linting
4. Sorted imports
5. Trailing commas in multi-line calls

**Common auto-fixes:**
- Import reordering
- Trailing comma addition
- Whitespace cleanup

**Tip:** Let hooks auto-fix, then commit. Don't fight the formatter.

---

## Reference

### Syslog Priority Calculation

**Formula:** `priority = facility * 8 + level`

**Common Facilities:**
- `kern=0`, `user=1`, `mail=2`, `daemon=3`
- `auth=4`, `syslog=5`, `lpr=6`, `news=7`

**Common Levels:**
- `emerg=0`, `alert=1`, `crit=2`, `err=3`
- `warning=4`, `notice=5`, `info=6`, `debug=7`

**Examples:**

```python

PRI_SYSLOG_ALERT = 41  # facility=5 (syslog) * 8 + level=1 (alert)
PRI_KERN_DEBUG = 7     # facility=0 (kern) * 8 + level=7 (debug)
PRI_DAEMON_ALERT = 25  # facility=3 (daemon) * 8 + level=1 (alert)

```

### SSL/TLS in Tests

**For legacy compatibility tests** (SocketSender):
- Uses `ssl.PROTOCOL_TLSv1_2` (deprecated but compatible)
- No certificate verification by default
- See `tests/light/src/message_senders/README.md`

**For new tests** - use Config API:

```python

source = config.create_network_source(
    transport="tls",
    tls={
        "key-file": copy_shared_file(testcase_parameters, "server.key"),
        "cert-file": copy_shared_file(testcase_parameters, "server.crt"),
        "peer-verify": '"optional-untrusted"',
    },
)

```

### Filter Syntax

**Single value:**

```python

config.create_filter("facility(syslog)")
config.create_filter("level(debug)")
config.create_filter("host('server1')")

```

**Multiple values:**

```python

config.create_filter("facility(daemon,auth,lpr)")
config.create_filter("level(err,crit,alert)")

```

**Range:**

```python

config.create_filter("level(warning..crit)")  # warning, err, crit

```

### Multiple Sources in Logpath

```python

config.create_logpath(statements=[
    source1,
    source2,
    source3,
    parser,
    filter_obj,
    dest,
])

```

Equivalent config:

```text

log {
    source(source1);
    source(source2);
    source(source3);
    parser { ... };
    filter { ... };
    destination { ... };
};

```

---

## Multiplatform Compatibility

syslog-ng runs on **Linux** (many distributions), **macOS**, and **FreeBSD**. Tests must pass on all supported platforms. CI runs on multiple platforms, so platform-specific failures block merges.

### Rules

#### 1. Never Assume Linux-Only Behavior

- Do not assume `/proc`, `/sys`, or `/dev/log` exist.
- Do not assume `systemd` or `journald` are available.
- Do not assume GNU coreutils behavior (e.g., `date`, `stat` differ on macOS/BSD).
- Do not hardcode Linux-specific paths (`/etc/os-release`, `/run/`, etc.).

#### 2. File Paths and Separators

- Use `os.path.join()` for path construction, never string concatenation with `/`.
- Do not assume `/tmp` is writable — use `tmp_path` pytest fixture instead.
- Do not assume specific permissions or ownership behavior.

#### 3. Shell and System Commands

- Avoid shell=True subprocess calls with Linux-specific commands.
- If you must run a system command, check the platform first:

```python

import platform
import subprocess

if platform.system() == "Linux":
    # Linux-specific command
elif platform.system() == "Darwin":
    # macOS-specific command
elif platform.system() == "FreeBSD":
    # FreeBSD-specific command

```

- Prefer Python stdlib over shell commands whenever possible.

#### 4. Networking

- Do not bind to specific interfaces that may not exist (`eth0`, `lo`).
- Use `localhost` / `127.0.0.1` for local networking.
- Always use the `port_allocator()` fixture for ports; never hardcode port numbers.

#### 5. Timing and Signals

- Signal numbers differ between platforms — use the `signal` module constants (`signal.SIGTERM`) instead of raw integers.
- Add adequate settling time when relying on filesystem events (inotify is Linux-only; kqueue is used on macOS/BSD, and behavior differs).

#### 6. Python Standard Library Portability

- Avoid `fcntl`, `termios`, `grp`, `pwd` without first guarding with `if platform.system() != "Windows"` (these are unavailable on Windows; additionally some APIs differ between BSDs and Linux).
- Use `pathlib.Path` instead of `os.path` where possible for cleaner cross-platform code.

### Detecting the Platform in Tests

```python

import platform
import pytest

@pytest.mark.skipif(
    platform.system() != "Linux",
    reason="inotify is Linux-only",
)
def test_inotify_behavior(config, syslog_ng):
    ...

```

Use `pytest.mark.skipif` sparingly — prefer writing tests that work everywhere. Only skip when a feature is genuinely unavailable on a platform.

### macOS-Specific Gotchas

- No `epoll` — use `kqueue`/`select` based polling; syslog-ng handles this, but tests should not rely on epoll.
- `getent` is not available by default; use Python's `pwd`/`grp` modules instead.
- Default `ulimit` values are lower than on Linux — avoid opening many file handles in tests.
- `SO_REUSEPORT` behavior differs; prefer `SO_REUSEADDR`.

### FreeBSD-Specific Gotchas

- `/dev/log` may not exist or behave differently; avoid relying on it in tests.
- `sendfile()` semantics differ; file source tests should not assume Linux semantics.
- Jails may restrict certain syscalls; tests should not require root or special capabilities.

### Multiplatform Checklist

Add these to the per-test review:

- [ ] No hardcoded Linux paths (`/proc`, `/sys`, `/dev/log`, `/run`)
- [ ] No Linux-only signal numbers (use `signal.SIGTERM` etc.)
- [ ] No `inotify` assumed without a platform guard
- [ ] Paths built with `os.path.join()` or `pathlib`
- [ ] Ports allocated via `port_allocator()`, never hardcoded
- [ ] Temp files use `tmp_path` fixture, not hardcoded `/tmp/...`
- [ ] Any `platform.system()` skip markers have a clear justification

---

## Checklist for New Tests

Before submitting a new test:

**Before Starting:**
- [ ] Check for existing tests in `tests/light/functional_tests/`
- [ ] Verify functionality isn't already covered

**Implementation:**
- [ ] Choose correct source type (example-msg-generator preferred)
- [ ] Use Config API unless feature requires raw config
- [ ] Include `freq=0` for example-msg-generator
- [ ] Add syslog-parser before facility/level filters
- [ ] Use unique persist-name for shared destinations
- [ ] Use `read_logs(n)` for multiple messages
- [ ] Place test in appropriate subdirectory

**Code Quality:**
- [ ] No magic numbers (use named constants)
- [ ] Extract repeated code into helpers
- [ ] Use config template functions if needed
- [ ] Keep test functions under 20 lines
- [ ] Add descriptive comments (not docstrings for compatibility)

**Validation:**
- [ ] Test passes in isolation
- [ ] Run all tests in module (no conflicts)
- [ ] Run `make light-linters` (no style errors)

**Multiplatform:**
- [ ] No hardcoded Linux-only paths or assumptions
- [ ] Platform skips (`pytest.mark.skipif`) are justified and minimal
- [ ] Ports allocated via `port_allocator()`, temp files via `tmp_path`
- [ ] Signal constants used (`signal.SIGTERM`), not raw integers

**Distribution (Optional):**
- [ ] Add test to `functional_tests/Makefile.am` EXTRA_DIST
