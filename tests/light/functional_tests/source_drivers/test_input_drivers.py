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
import gc
import os
import re
import subprocess
import time
from socket import AF_INET
from socket import AF_UNIX

from src.common.file import copy_shared_file
from src.message_senders import FileSender
from src.message_senders import SocketSender

# Constants
MESSAGE = 'input_drivers'
MESSAGE_NEW = 'input_drivers_new'
REPEAT_COUNT = 100  # Number of messages each sender will send
SETTLE_TIME = 6  # Time to wait for all messages to be processed

# Syslog message prefixes (from original functional test)
SYSLOG_PREFIX = "2004-09-07T10:43:21+01:00 bzorp prog[12345]:"
SYSLOG_NEW_PREFIX = "2004-09-07T10:43:21+01:00 bzorp prog 12345 - -"


def create_named_pipes():
    """Create named pipes for pipe source testing."""
    pipes = ['log-pipe', 'log-padded-pipe']
    for pipe in pipes:
        if not os.path.exists(pipe):
            subprocess.run(['mkfifo', pipe], check=True)


def check_file_expected(filename, expected_messages, syslog_prefix, skip_prefix=0):
    """Validate log file contains expected messages in correct order.

    Args:
        filename: Path to log file to check
        expected_messages: List of tuples [(msg, session, count), ...]
        syslog_prefix: Expected syslog prefix in each line
        skip_prefix: Number of characters to skip before syslog_prefix

    Returns:
        True if validation passes, False otherwise
    """
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File not found: {filename}")
        return False

    # Track message matches: {(msg, session): last_id}
    matches = {}
    prefix_len = len(syslog_prefix)

    for lineno, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        # Check syslog prefix
        if line[skip_prefix:prefix_len + skip_prefix] != syslog_prefix:
            print(f"Line {lineno} missing syslog prefix: {line}")
            return False

        # Extract message payload
        msg_payload = line[skip_prefix + prefix_len:]

        # Parse: " <msg> <session>/<id> ..."
        m = re.match(r'^ (\S+) (\d+)/(\d+)', msg_payload)
        if not m:
            print(f"Line {lineno} unexpected format: {line}")
            return False

        msg = m.group(1)
        session = int(m.group(2))
        msg_id = int(m.group(3))

        # Validate message ordering within session
        if (msg, session) not in matches:
            if msg_id != 1:
                print(f"First message ID not 1: session={session}, id={msg_id}")
                return False
        else:
            if matches[(msg, session)] != msg_id - 1:
                print(f"Message reordering detected: session={session}, id={msg_id}, expected={matches[(msg, session)] + 1}")
                return False

        matches[(msg, session)] = msg_id

    # Validate all expected messages are present with correct counts
    for msg, session, count in expected_messages:
        if (msg, session) not in matches:
            print(f"Missing message: msg={msg}, session={session}, count={count}")
            return False
        if matches[(msg, session)] != count - 1:
            print(f"Wrong message count: msg={msg}, session={session}, got={matches[(msg, session)]}, expected={count - 1}")
            return False
        del matches[(msg, session)]

    # Check for unexpected messages
    if len(matches) > 0:
        print(f"Unexpected messages found: {matches}")
        return False

    return True


def test_input_drivers(config, syslog_ng, port_allocator, testcase_parameters, teardown):
    """Test various input source drivers with different protocols and transports.

    Tests:
    - Unix domain sockets (stream and datagram)
    - Internet sockets (TCP and UDP, including SSL/TLS)
    - Named pipes (regular and padded)
    - File sources
    - RFC3164 and RFC5424 syslog formats
    """
    # Allocate ports for network sources
    tcp_udp_port = port_allocator()
    ssl_port = port_allocator()
    network_port = port_allocator()
    syslog_port = port_allocator()

    # Copy SSL certificates from shared_files
    server_key_path = copy_shared_file(testcase_parameters, "server.key")
    server_cert_path = copy_shared_file(testcase_parameters, "server.crt")

    # Create named pipes before starting syslog-ng
    create_named_pipes()

    # Configure syslog-ng with all source types
    raw_config = f"""
@version: {config.get_version()}

options {{
    ts_format(iso);
    chain_hostnames(no);
    keep_hostname(yes);
    threaded(yes);
}};

source s_int {{
    internal();
}};

source s_unix {{
    unix-stream("log-stream" flags(expect-hostname) listen-backlog(64));
    unix-dgram("log-dgram" flags(expect-hostname));
}};

source s_inet {{
    tcp(port({tcp_udp_port}) listen-backlog(64));
    udp(port({tcp_udp_port}) so-rcvbuf(131072));
}};

source s_inetssl {{
    tcp(port({ssl_port}) tls(peer-verify(none) cert-file("{server_cert_path}") key-file("{server_key_path}")));
}};

source s_pipe {{
    pipe("log-pipe" flags(expect-hostname));
    pipe("log-padded-pipe" pad-size(2048) flags(expect-hostname));
}};

source s_file {{
    file("log-file");
}};

source s_network {{
    network(transport(udp) port({network_port}));
    network(transport(tcp) listen-backlog(64) port({network_port}));
}};

source s_syslog {{
    syslog(port({syslog_port}) transport("tcp") so-rcvbuf(131072));
    syslog(port({syslog_port}) transport("udp") so-rcvbuf(131072));
}};

filter f_input1 {{
    message("{MESSAGE}");
}};

filter f_input1_new {{
    message("{MESSAGE_NEW}");
}};

destination d_input1 {{
    file("test-input1.log");
}};

destination d_input1_new {{
    file("test-input1_new.log" flags(syslog-protocol));
}};

log {{
    source(s_int);
    source(s_unix);
    source(s_inet);
    source(s_inetssl);
    source(s_pipe);
    source(s_file);
    source(s_network);
    log {{
        filter(f_input1);
        destination(d_input1);
    }};
}};

log {{
    source(s_syslog);
    log {{
        filter(f_input1_new);
        destination(d_input1_new);
    }};
}};
"""

    config.set_raw_config(raw_config)

    # Disable debug mode to prevent internal messages polluting log files
    # Also disable stderr checking since many connections take time to close
    syslog_ng.start_params.debug = False
    syslog_ng.start_params.stderr = False
    syslog_ng.start_params.trace = False
    syslog_ng.start_params.verbose = False

    syslog_ng.start(config)

    # Wait for syslog-ng to be ready
    time.sleep(2)

    # Define all senders
    senders = (
        SocketSender(AF_UNIX, 'log-dgram', dgram=1, terminate_seq='\n', repeat=REPEAT_COUNT),
        SocketSender(AF_UNIX, 'log-dgram', dgram=1, terminate_seq='\0', repeat=REPEAT_COUNT),
        SocketSender(AF_UNIX, 'log-dgram', dgram=1, terminate_seq='\0\n', repeat=REPEAT_COUNT),
        SocketSender(AF_UNIX, 'log-dgram', dgram=1, terminate_seq='', repeat=REPEAT_COUNT),
        SocketSender(AF_UNIX, 'log-stream', dgram=0, repeat=REPEAT_COUNT),
        SocketSender(AF_UNIX, 'log-stream', dgram=0, send_by_bytes=1, repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', tcp_udp_port), dgram=1, terminate_seq='\n', repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', tcp_udp_port), dgram=1, terminate_seq='\0', repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', tcp_udp_port), dgram=1, terminate_seq='\0\n', repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', tcp_udp_port), dgram=1, terminate_seq='', repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', tcp_udp_port), dgram=0, repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', tcp_udp_port), dgram=0, send_by_bytes=1, repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', ssl_port), dgram=0, ssl_enabled=1, repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', ssl_port), dgram=0, send_by_bytes=1, ssl_enabled=1, repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', network_port), dgram=1, terminate_seq='\n', repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', network_port), dgram=0, repeat=REPEAT_COUNT),
        FileSender('log-pipe', repeat=REPEAT_COUNT),
        FileSender('log-pipe', send_by_bytes=1, repeat=REPEAT_COUNT),
        FileSender('log-padded-pipe', padding=2048, repeat=REPEAT_COUNT),
        FileSender('log-padded-pipe', padding=2048, repeat=REPEAT_COUNT),
        FileSender('log-file', repeat=REPEAT_COUNT),
        FileSender('log-file', send_by_bytes=1, repeat=REPEAT_COUNT),
    )

    senders_new = (
        SocketSender(AF_INET, ('localhost', syslog_port), dgram=1, new_protocol=1, terminate_seq='', repeat=REPEAT_COUNT),
        SocketSender(AF_INET, ('localhost', syslog_port), dgram=0, new_protocol=1, terminate_seq='', repeat=REPEAT_COUNT),
    )

    # Register cleanup to close file descriptors even on test failure
    def cleanup_senders():
        # Force garbage collection to close FileSender file descriptors
        gc.collect()

    teardown.register(cleanup_senders)

    # Send messages through all senders and collect expected results
    expected = []
    for sender in senders:
        expected.extend(sender.sendMessages(MESSAGE))

    expected_new = []
    for sender in senders_new:
        expected_new.extend(sender.sendMessages(MESSAGE_NEW))

    # Wait for all messages to be processed
    time.sleep(SETTLE_TIME)

    # Validate RFC3164 messages (old syslog protocol)
    assert check_file_expected("test-input1.log", expected, SYSLOG_PREFIX), \
        "RFC3164 message validation failed"

    # Validate RFC5424 messages (new syslog protocol)
    assert check_file_expected("test-input1_new.log", expected_new, SYSLOG_NEW_PREFIX, skip_prefix=len('<7>1 ')), \
        "RFC5424 message validation failed"
