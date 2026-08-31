#!/usr/bin/env python
#############################################################################
# Copyright (c) 2015-2019 Balabit
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
from socket import AF_INET
from socket import AF_UNIX

from src.message_senders import FileSender
from src.message_senders import SocketSender


# Constants for message senders
REPEAT_COUNT = 10


def create_named_pipes():
    """Create named pipes required for file sources."""
    for pipe in ('log-pipe', 'log-padded-pipe'):
        try:
            os.unlink(pipe)
        except OSError:
            pass
        os.mkfifo(pipe)


# Test catch-all flag with single file source.
#
def test_flags_catch_all(config, syslog_ng, log_message, bsd_formatter):
    file_source = config.create_file_source(file_name="input.log")
    file_destination = config.create_file_destination(
        file_name="output.log",
    )
    catch_all_destination = config.create_file_destination(
        file_name="catchall_output.log",
    )

    inner_logpath = config.create_inner_logpath(statements=[file_destination])

    config.create_logpath(statements=[file_source, inner_logpath])
    config.create_logpath(
        statements=[catch_all_destination],
        flags="catch-all",
    )
    config.update_global_options(keep_hostname="yes")

    input_message = bsd_formatter.format_message(log_message)
    expected_message = bsd_formatter.format_message(
        log_message.remove_priority(),
    )
    file_source.write_log(input_message)

    syslog_ng.start(config)

    destination_log = file_destination.read_log()
    # message should arrived into destination1
    assert expected_message in destination_log

    catch_all_destination_log = catch_all_destination.read_log()
    # message should arrived into catch_all_destination
    # there is a flags(catch-all)
    assert expected_message in catch_all_destination_log


# Test catch-all flag with multiple heterogeneous source types.
# Legacy backport from tests/functional - uses SocketSender/FileSender.
# TODO: Refactor to modern light framework patterns.
#
def test_flags_catch_all_multiple_sources(config, syslog_ng, port_allocator):
    # Allocate ports for network sources
    tcp_port = port_allocator()

    # Create named pipes before starting syslog-ng
    create_named_pipes()

    # Configure syslog-ng with multiple sources and catch-all logpath
    raw_config = f"""
@version: {config.get_version()}

options {{
    ts_format(iso);
    chain_hostnames(no);
    keep_hostname(yes);
    threaded(yes);
}};

# Sources for various input types
source s_int {{ internal(); }};
source s_unix {{
    unix-stream("log-stream" flags(expect-hostname) listen-backlog(64));
    unix-dgram("log-dgram" flags(expect-hostname));
}};
source s_inet {{
    tcp(port({tcp_port}) listen-backlog(64));
    udp(port({tcp_port}) so_rcvbuf(131072));
}};
source s_pipe {{
    pipe("log-pipe" flags(expect-hostname));
    pipe("log-padded-pipe" pad_size(2048) flags(expect-hostname));
}};

# Catch-all specific source (not connected to other logpaths)
source s_catchall {{
    unix-stream("log-stream-catchall" flags(expect-hostname));
}};

# Filter for catch-all test messages
filter f_catchall {{ message("catchall"); }};

# Destination for catch-all messages
destination d_catchall {{ file("test-catchall.log"); }};

# Dummy destination for regular logpath (messages won't match filter)
destination d_dummy {{ file("test-dummy.log"); }};

# Regular logpaths (for other sources, won't match catch-all filter)
log {{
    source(s_int);
    source(s_unix);
    source(s_inet);
    source(s_pipe);
    destination(d_dummy);
}};

# Catch-all logpath - receives ALL messages matching filter
log {{ filter(f_catchall); destination(d_catchall); flags(catch-all); }};
"""

    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Wait for all listeners (TCP, Unix sockets, pipes) to be ready
    time.sleep(4)

    # Create 15 different senders (original test compatibility)
    senders = (
        SocketSender(
            AF_UNIX, 'log-stream-catchall',
            dgram=0, send_by_bytes=1, repeat=REPEAT_COUNT,
        ),
        SocketSender(AF_UNIX, 'log-dgram', dgram=1, repeat=REPEAT_COUNT),
        SocketSender(
            AF_UNIX, 'log-dgram',
            dgram=1, terminate_seq='\0', repeat=REPEAT_COUNT,
        ),
        SocketSender(
            AF_UNIX, 'log-dgram',
            dgram=1, terminate_seq='\0\n', repeat=REPEAT_COUNT,
        ),
        SocketSender(AF_UNIX, 'log-stream', dgram=0, repeat=REPEAT_COUNT),
        SocketSender(
            AF_UNIX, 'log-stream',
            dgram=0, send_by_bytes=1, repeat=REPEAT_COUNT,
        ),
        SocketSender(
            AF_INET, ('localhost', tcp_port),
            dgram=1, repeat=REPEAT_COUNT,
        ),
        SocketSender(
            AF_INET, ('localhost', tcp_port),
            dgram=1, terminate_seq='\0', repeat=REPEAT_COUNT,
        ),
        SocketSender(
            AF_INET, ('localhost', tcp_port),
            dgram=1, terminate_seq='\0\n', repeat=REPEAT_COUNT,
        ),
        SocketSender(
            AF_INET, ('localhost', tcp_port),
            dgram=0, repeat=REPEAT_COUNT,
        ),
        SocketSender(
            AF_INET, ('localhost', tcp_port),
            dgram=0, send_by_bytes=1, repeat=REPEAT_COUNT,
        ),
        FileSender('log-pipe', repeat=REPEAT_COUNT),
        FileSender('log-pipe', send_by_bytes=1, repeat=REPEAT_COUNT),
        FileSender('log-padded-pipe', padding=2048, repeat=REPEAT_COUNT),
        FileSender('log-padded-pipe', padding=2048, repeat=REPEAT_COUNT),
    )

    # Send messages from all senders
    message = 'catchall'
    for sender in senders:
        sender.sendMessages(message)

    # Calculate expected message count
    # Each sender sends (REPEAT_COUNT - 1) messages
    expected_count = len(senders) * (REPEAT_COUNT - 1)

    # Read and validate catch-all destination
    # Allow time for all messages to arrive
    time.sleep(3)

    with open("test-catchall.log", 'r') as f:
        logs = f.readlines()

    # Verify all messages arrived
    assert len(logs) == expected_count, (
        f"Expected {expected_count} messages in catch-all log, "
        f"got {len(logs)}"
    )

    # Verify message content (all should contain 'catchall')
    for log in logs:
        assert 'catchall' in log, f"Message missing 'catchall': {log}"
