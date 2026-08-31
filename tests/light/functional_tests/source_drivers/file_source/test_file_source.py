#!/usr/bin/env python
#############################################################################
# Copyright (c) 2007-2015 Balabit
# Copyright (c) 2026 OneIdentity
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 as published
# by the Free Software Foundation, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
# As an additional exemption you are allowed to compile & link against the
# OpenSSL libraries as published by the OpenSSL project. See the file
# COPYING for details.
#
#############################################################################
import os
import shutil
import time

# Constants
NUM_MESSAGES_PER_FILE = 100
SETTLE_TIME = 4
RUNTIME_DETECTION_SETTLE_TIME = 5


def create_wildcard_file_config(
    version,
    base_dir="wildcard",
    filename_pattern="*.log",
    exclude_pattern=None,
    monitor_method="auto",
    recursive=True,
    output_file="test-wildcard.log",
):
    """Generate wildcard-file source configuration."""
    exclude_clause = f'exclude-pattern("{exclude_pattern}")' if exclude_pattern else ""

    return f"""
@version: {version}

options {{
    ts_format(iso);
    chain_hostnames(no);
    keep_hostname(yes);
}};

source s_wildcard {{
    wildcard-file(
        base-dir("{base_dir}")
        filename-pattern("{filename_pattern}")
        {exclude_clause}
        monitor-method("{monitor_method}")
        recursive({'yes' if recursive else 'no'})
    );
}};

destination d_wildcard {{
    file("{output_file}");
}};

log {{
    source(s_wildcard);
    destination(d_wildcard);
}};
"""


def create_source_files(recursive=False):
    """Helper function to create test files with messages."""
    messages = [
        'wildcard0',
        'wildcard1',
        'wildcard2',
        'wildcard3',
        'wildcard4',
        'wildcard5',
        'wildcard6',
        'wildcard7',
    ]
    expected = []

    for ndx, msg in enumerate(messages):
        if not recursive:
            # Non-recursive: wildcard/0.log, wildcard/1.log, etc. (4 files total)
            file_path = f"wildcard/{ndx % 4}.log"
        else:
            # Recursive: wildcard/wildcard0/0.log, wildcard/wildcard1/1.log, etc.
            file_path = f"wildcard/wildcard{ndx % 2}/{ndx % 4}.log"

        # Create directory if needed
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Write messages (append mode since multiple messages may go to same file)
        with open(file_path, 'a') as f:
            for _ in range(NUM_MESSAGES_PER_FILE):
                f.write(f"{msg}\n")
                expected.append(msg)

    return expected


def validate_output(output_file, expected):
    """Validate that output file contains expected messages."""
    assert os.path.exists(output_file), f"Output file {output_file} does not exist"

    with open(output_file, 'r') as f:
        output_lines = f.readlines()

    # Count occurrences of each message in both expected and actual output
    from collections import Counter
    expected_counts = Counter(expected)
    actual_counts = Counter()

    for line in output_lines:
        for msg in expected_counts:
            if msg in line:
                actual_counts[msg] += 1
                break  # Each line should match only one message

    # Verify counts match for each message
    assert actual_counts == expected_counts, \
        f"Message counts mismatch.\nExpected: {dict(expected_counts)}\nActual: {dict(actual_counts)}"


# Test wildcard-file source with non-recursive directory scanning.
#
def test_wildcard_files(config, syslog_ng):
    """Test wildcard-file source with basic wildcard matching."""

    # Create files before starting syslog-ng
    expected = create_source_files(recursive=False)

    # Configure and start
    raw_config = create_wildcard_file_config(config.get_version())
    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Wait and validate
    time.sleep(SETTLE_TIME)
    validate_output("test-wildcard.log", expected)


# Test wildcard-file source with recursive directory scanning.
#
def test_wildcard_recursion(config, syslog_ng):
    """Test wildcard-file source with recursive directory matching."""

    # Create files in subdirectories
    expected = create_source_files(recursive=True)

    # Configure and start
    raw_config = create_wildcard_file_config(config.get_version())
    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Wait and validate
    time.sleep(SETTLE_TIME)
    validate_output("test-wildcard.log", expected)


# Test wildcard-file source handles case where base directory doesn't exist at startup.
#
def test_wildcard_no_directory_exists(config, syslog_ng):
    """Test wildcard-file source when directory is created after syslog-ng starts."""

    # Remove wildcard directory if it exists
    if os.path.exists("wildcard"):
        shutil.rmtree("wildcard")

    # Configure and start (directory doesn't exist yet)
    raw_config = create_wildcard_file_config(config.get_version())
    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Now create the directory and files
    expected = create_source_files(recursive=False)

    # Wait and validate
    time.sleep(SETTLE_TIME)
    validate_output("test-wildcard.log", expected)


# Test wildcard-file source detects files created after syslog-ng starts.
#
def test_wildcard_runtime_detection(config, syslog_ng):
    """Test wildcard-file source detects files created at runtime."""

    # Create directory but no files yet
    os.makedirs("wildcard", exist_ok=True)

    # Configure and start (no files exist yet)
    raw_config = create_wildcard_file_config(config.get_version())
    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Now create files after syslog-ng has started
    expected = create_source_files(recursive=False)

    # Wait longer for runtime detection
    time.sleep(RUNTIME_DETECTION_SETTLE_TIME)
    validate_output("test-wildcard.log", expected)
