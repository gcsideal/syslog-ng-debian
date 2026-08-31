#!/usr/bin/env python
#############################################################################
# Copyright (c) 2017 Balabit
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
# Constants for test
NUM_MESSAGES = 2


# Test for map-value-pairs parser with key rewriting. This test verifies that the parser correctly rewrites keys
# and that the rewritten keys can be accessed in the destination template.
#
def test_map_value_pairs(config, syslog_ng):
    """Test map-value-pairs parser with key rewriting."""

    # Use pure raw config since map-value-pairs doesn't have a config API helper
    # and mixing config API with raw config causes issues
    raw_config = f"""
@version: {config.get_version()}

source s_generator {{
    example-msg-generator(
        num({NUM_MESSAGES})
        freq(0)
        template("test_message")
    );
}};

parser p_map {{
    map-value-pairs(key("MSG*" rekey(add-prefix("foo."))));
}};

destination d_file {{
    file("test-map-value-pairs.log" template("${{foo.MSG}}\\n"));
}};

log {{
    source(s_generator);
    parser(p_map);
    destination(d_file);
}};
"""

    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Read output file directly since we used raw config
    # The test runs in the working directory, so files are relative to current dir
    import os
    import time
    time.sleep(1)  # Give syslog-ng time to write

    log_file = "test-map-value-pairs.log"
    assert os.path.exists(log_file), f"Log file {log_file} does not exist"

    with open(log_file, 'r') as f:
        logs = f.readlines()

    assert len(logs) == NUM_MESSAGES, f"Expected {NUM_MESSAGES} messages, got {len(logs)}"

    # Verify that the messages contain the message content (accessed via foo.MSG)
    for log in logs:
        assert "test_message" in log, f"Expected 'test_message' in log: {log}"
