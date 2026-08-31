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
import re
import time

# Constants
LOGGEN_RATE = 1000000
MESSAGE_SIZE = 160
INTERVAL_SECONDS = 10
MIN_EXPECTED_RATE = 100  # Minimum messages/sec expected even on slow systems


def parse_loggen_rate(loggen_stderr_path):
    """Extract the message rate from loggen stderr output."""
    with open(loggen_stderr_path, 'r') as f:
        output = f.read()

    # Pattern: "rate = XXX.XX" in loggen output
    match = re.search(r'rate\s*=\s*([0-9.]+)', output)
    if match:
        return float(match.group(1))

    raise ValueError(f"Could not parse rate from loggen output: {output}")


# Test basic TCP source performance using loggen.
#
def test_performance(config, syslog_ng, port_allocator, loggen):
    """Test syslog-ng performance with high-rate message generation."""

    server_port = port_allocator()

    raw_config = f"""
@version: {config.get_version()}

options {{
    ts_format(iso);
    chain_hostnames(no);
    keep_hostname(yes);
    threaded(yes);
}};

source s_tcp {{
    tcp(port({server_port}));
}};

destination d_file {{
    file("test-performance.log");
}};

log {{
    source(s_tcp);
    destination(d_file);
}};
"""

    config.set_raw_config(raw_config)

    # Disable verbose mode to skip waiting for "shutting down" message during teardown
    # Performance tests generate huge message volumes that take too long to flush
    syslog_ng.start_params.verbose = False

    syslog_ng.start(config)

    # Wait for syslog-ng to start listening on the TCP port
    # When verbose=False, start() doesn't wait for the startup message
    time.sleep(2)

    # Start loggen to generate high-rate traffic
    loggen.start(
        "127.0.0.1",
        str(server_port),
        inet=True,
        stream=True,
        rate=LOGGEN_RATE,
        size=MESSAGE_SIZE,
        interval=INTERVAL_SECONDS,
        active_connections=1,
        quiet=True,
    )

    # Wait for loggen to complete
    time.sleep(INTERVAL_SECONDS + 2)

    # Stop loggen to ensure clean completion
    loggen.stop()

    # Parse loggen output to get actual message rate
    rate = parse_loggen_rate(loggen.loggen_stderr_path)

    # Assert minimum performance threshold
    assert rate > MIN_EXPECTED_RATE, \
        f"Performance too low: {rate:.2f} msg/sec (expected > {MIN_EXPECTED_RATE})"
