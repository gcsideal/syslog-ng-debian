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
import time

# Constants
NUM_MESSAGES_PER_FILE = 100
SETTLE_TIME = 4
OUTPUT_FILE = "test-wildcard.log"


def create_wildcard_file_config(version, exclude_pattern):
    """Generate wildcard-file source configuration with exclude pattern."""
    return f"""
@version: {version}

options {{
    ts_format(iso);
    chain_hostnames(no);
    keep_hostname(yes);
}};

source s_wildcard {{
    wildcard-file(
        base-dir("wildcard")
        filename-pattern("*.log")
        exclude-pattern("{exclude_pattern}")
        monitor-method("auto")
        recursive(yes)
    );
}};

destination d_wildcard {{
    file("{OUTPUT_FILE}");
}};

log {{
    source(s_wildcard);
    destination(d_wildcard);
}};
"""


def create_files_with_messages(file_paths, messages):
    """Create files with repeated messages."""
    expected = []
    for file_path, msg in zip(file_paths, messages):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'a') as f:
            for _ in range(NUM_MESSAGES_PER_FILE):
                f.write(f"{msg}\n")
                expected.append(msg)
    return expected


def validate_messages_absent(output_lines, messages):
    """Validate that excluded messages are NOT present in output."""
    for msg in messages:
        found = any(msg in line for line in output_lines)
        assert not found, f"Excluded message '{msg}' should not appear in output but was found"


# Test wildcard-file source with exclude-pattern to verify files matching the
# exclude pattern are not processed while matching files are.
#
def test_excluded_files(config, syslog_ng):
    """Test wildcard-file source with exclude-pattern."""

    # Messages for included files
    included_messages = [
        'wildcard0', 'wildcard1', 'wildcard2', 'wildcard3',
        'wildcard4', 'wildcard5', 'wildcard6', 'wildcard7',
    ]

    # Messages for excluded files (should NOT appear)
    excluded_messages = [
        'excluded0', 'excluded1', 'excluded2', 'excluded3',
        'excluded4', 'excluded5', 'excluded6', 'excluded7',
    ]

    # Create included files: wildcard/wildcard0/0.log, wildcard/wildcard1/1.log, etc.
    included_paths = [
        f"wildcard/wildcard{ndx % 2}/{ndx % 4}.log"
        for ndx in range(len(included_messages))
    ]
    expected = create_files_with_messages(included_paths, included_messages)

    # Create excluded files: wildcard/wildcard0/excluded.0.log, etc.
    # These match pattern "*.?.log" and should be excluded
    excluded_paths = [
        f"wildcard/wildcard{ndx % 2}/excluded.{ndx % 4}.log"
        for ndx in range(len(excluded_messages))
    ]
    create_files_with_messages(excluded_paths, excluded_messages)

    # Configure with exclude-pattern
    raw_config = create_wildcard_file_config(config.get_version(), exclude_pattern="*.?.log")
    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Wait for processing
    time.sleep(SETTLE_TIME)

    # Validate output
    assert os.path.exists(OUTPUT_FILE), f"Output file {OUTPUT_FILE} does not exist"

    with open(OUTPUT_FILE, 'r') as f:
        output_lines = f.readlines()

    # Count per-message occurrences to catch imbalanced distributions
    from collections import Counter
    expected_counts = Counter(expected)
    actual_counts = Counter()

    for line in output_lines:
        for msg in expected_counts:
            if msg in line:
                actual_counts[msg] += 1
                break

    # Verify exact per-message counts
    assert actual_counts == expected_counts, \
        f"Message counts mismatch.\nExpected: {dict(expected_counts)}\nActual: {dict(actual_counts)}"

    # Excluded messages should NOT be present
    validate_messages_absent(output_lines, excluded_messages)
