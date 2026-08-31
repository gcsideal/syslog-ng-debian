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
import re
import shutil
import sqlite3  # noqa: F401 - Used later for DB validation
import sys
from socket import AF_INET

import pytest

from src.common.blocking import wait_until_true
from src.message_senders import SocketSender


def has_afsql_module(syslog_ng):
    """Check if afsql module is available."""
    # TODO: Implement module registry check
    # For now, assume it's available if syslog-ng starts
    return True


def find_sqlite3_cli():
    """Find sqlite3 CLI tool."""
    return shutil.which('sqlite3')


def find_libdbi_sqlite3():
    """Find libdbi sqlite3 backend library."""
    soext = '.so'
    if re.match('hp-ux', sys.platform) and not re.match('ia64', os.uname()[4]):
        soext = '.sl'

    paths = (
        os.environ.get('dbd_dir', ''),
        '/usr/local/lib/dbd',
        '/usr/lib/dbd',
        '/usr/lib64/dbd/',
        '/opt/syslog-ng/lib/dbd',
        '/opt/homebrew/lib/dbd',
        '/usr/lib/x86_64-linux-gnu/dbd',
        '/usr/lib/aarch64-linux-gnu/dbd',
    )

    for pth in paths:
        if pth and os.path.isfile(f'{pth}/libdbdsqlite3{soext}'):
            return f'{pth}/libdbdsqlite3{soext}'

    return None


def check_sql_expected(db_path, table, expected_messages):
    """Validate that expected messages are in the SQL database.

    Args:
        db_path: Path to the sqlite3 database file
        table: Table name to query
        expected_messages: List of tuples (message, session_counter, count)

    Returns:
        True if all expected messages found, False otherwise
    """
    if not os.path.exists(db_path):
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Query all rows from the table (return False if table doesn't exist yet)
        try:
            cursor.execute(f"SELECT date, host, program, pid, msg FROM {table}")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            return False

        # The message payload format produced by MessageSender is:
        #   "<msg> <SSS>/<IIIII> ..."
        # For each (msg, session) group we must observe ids 1..count-1 exactly
        # once, with no missing, duplicated, or unexpected (msg, session) groups
        # (mirrors the original tests/functional/messagecheck.py::check_contents
        # semantics, minus in-stream ordering since SQL rows are unordered).
        payload_re = re.compile(r"(\S+) (\d+)/(\d+)")
        seen: dict[tuple[str, int], set[int]] = {}
        for row in rows:
            msg_field = row[4]
            m = payload_re.search(msg_field)
            if not m:
                return False
            msg, session, msg_id = m.group(1), int(m.group(2)), int(m.group(3))
            ids = seen.setdefault((msg, session), set())
            if msg_id in ids:
                return False
            ids.add(msg_id)

        for expected_msg, session_counter, expected_count in expected_messages:
            ids = seen.pop((expected_msg, session_counter), None)
            if ids is None:
                return False
            if ids != set(range(1, expected_count)):
                return False

        return len(seen) == 0

    finally:
        conn.close()


@pytest.fixture(autouse=True)
def require_sql_dependencies(syslog_ng):
    """Skip test if SQL dependencies are not available."""
    if not has_afsql_module(syslog_ng):
        pytest.skip("afsql module not available")

    if not find_sqlite3_cli():
        pytest.skip("sqlite3 CLI tool not found")

    libdbi_path = find_libdbi_sqlite3()
    if not libdbi_path:
        pytest.skip("libdbi sqlite3 backend not found")


# Test SQL destination with sqlite3 backend.
#
def test_sql_basic(config, syslog_ng):
    """Basic SQL destination test - dependency check only."""
    # This test just verifies dependencies are available
    assert find_sqlite3_cli() is not None
    assert find_libdbi_sqlite3() is not None


# Test SQL destination with actual message sending.
#
def test_sql(config, syslog_ng, port_allocator):
    """Test SQL destination with sqlite3 backend."""
    db_path = "test-sql.db"
    tcp_port = port_allocator()
    dbi_driver_dir = os.path.dirname(find_libdbi_sqlite3())

    raw_config = f"""
@version: {config.get_version()}

options {{
    ts_format(iso);
    chain_hostnames(no);
    keep_hostname(yes);
    threaded(yes);
}};

source s_tcp {{
    tcp(port({tcp_port}));
}};

destination d_sql {{
    sql(type(sqlite3)
        database("{db_path}")
        dbi_driver_dir("{dbi_driver_dir}")
        host(dummy) port(1234) username(dummy) password(dummy)
        table("logs")
        null("@NULL@")
        columns("date datetime", "host", "program", "pid", "msg",
                "dummy int default 5678")
        values("$DATE", "$HOST", "$PROGRAM", "${{PID:-@NULL@}}",
               "$MSG", default)
        indexes("date", "host", "program")
        flags(explicit-commits)
        flush-lines(25)
        flush_timeout(100));
}};

log {{ source(s_tcp); destination(d_sql); }};
"""

    config.set_raw_config(raw_config)

    syslog_ng.start(config)

    # Send test messages
    messages = ['sql1', 'sql2']

    with SocketSender(AF_INET, ('localhost', tcp_port), dgram=0) as sender:
        expected = []
        for msg in messages:
            expected.extend(sender.sendMessages(msg, pri=7))

    # MessageSender.sendMessages() loops range(1, repeat) -> count-1 actual messages per call.
    expected_total = sum(count - 1 for _, _, count in expected)

    # Wait until afsql has committed every message. The `written` counter only
    # advances after a successful COMMIT (LTR_SUCCESS), unlike `processed`, which
    # is the input-side counter incremented when a message enters the worker queue
    # (LTR_QUEUED on every batched insert before flush). Without this wait the
    # final flush-timeout(100ms) batch can still be in flight when the DB is opened
    # for validation.
    stats_handler = config.stats_handler

    def dst_written_all():
        return stats_handler.get_stats("destination", "sql", "d_sql#0").get("written", 0) >= expected_total

    assert wait_until_true(dst_written_all), "afsql did not commit all messages"

    # Validate messages are in database
    assert check_sql_expected(db_path, "logs", expected)
