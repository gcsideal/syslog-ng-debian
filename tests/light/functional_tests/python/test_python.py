#!/usr/bin/env python
#############################################################################
# Copyright (c) 2015 Balabit
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
from pathlib import Path

import pytest

# Constants
NUM_MESSAGES = 2
FREQ_IMMEDIATE = 0
OUTPUT_FILE_DESTINATION = "test-python.log"
OUTPUT_FILE_PARSER = "test-python-parser.log"


@pytest.fixture(autouse=True)
def setup_env():
    """Setup PYTHONPATH so syslog-ng can find sngtestmod."""
    test_dir = str(Path(__file__).parent.absolute())

    # Save original PYTHONPATH
    original_pythonpath = os.environ.get('PYTHONPATH', '')

    # Add test directory to PYTHONPATH for syslog-ng subprocess
    if original_pythonpath:
        os.environ['PYTHONPATH'] = f"{test_dir}:{original_pythonpath}"
    else:
        os.environ['PYTHONPATH'] = test_dir

    yield

    # Restore original PYTHONPATH
    if original_pythonpath:
        os.environ['PYTHONPATH'] = original_pythonpath
    else:
        os.environ.pop('PYTHONPATH', None)


# Test Python destination with external module.
#
def test_python_destination(config, syslog_ng):
    """Test Python destination using sngtestmod.DestTest class."""

    raw_config = f"""
@version: {config.get_version()}
@module mod-python use-virtualenv(no)

options {{
    keep-hostname(yes);
}};

source s_gen {{
    example-msg-generator(
        num({NUM_MESSAGES})
        freq({FREQ_IMMEDIATE})
        template("test message ${{SEQNUM}}")
    );
}};

destination d_python {{
    python(
        class(sngtestmod.DestTest)
        value-pairs(
            key('MSG')
            pair('HOST', 'bzorp')
            pair('DATE', '$ISODATE')
            key('MSGHDR')
        )
    );
}};

log {{
    source(s_gen);
    destination(d_python);
}};
"""

    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Wait for messages to be processed and written
    import time
    time.sleep(2)

    # Stop syslog-ng to flush all buffers
    syslog_ng.stop()

    # Verify messages were written by Python destination
    output_file = Path(OUTPUT_FILE_DESTINATION)
    assert output_file.exists(), \
        f"Python destination did not create {OUTPUT_FILE_DESTINATION}"

    with open(output_file, 'r') as f:
        lines = f.readlines()

    assert len(lines) == NUM_MESSAGES, \
        f"Expected {NUM_MESSAGES} messages, got {len(lines)}"

    # Verify format: DATE HOST MSGHDRmessage
    for i, line in enumerate(lines, 1):
        assert "bzorp" in line, f"Line {i}: HOST not set to 'bzorp'"
        assert "test message" in line, f"Line {i}: MSG content incorrect"


# Test inline Python parser.
#
def test_python_parser(config, syslog_ng):
    """Test inline Python parser that copies MSG to FOOBAR field."""

    raw_config = f"""
@version: {config.get_version()}
@module mod-python use-virtualenv(no)

options {{
    keep-hostname(yes);
}};

source s_gen {{
    example-msg-generator(
        num({NUM_MESSAGES})
        freq({FREQ_IMMEDIATE})
        template("parser test ${{SEQNUM}}")
    );
}};

python {{

from syslogng import LogParser

class MyParser(LogParser):
    def init(self, options):
        return True

    def deinit(self):
        return True

    def parse(self, msg):
        msg['FOOBAR'] = msg['MSG']
        return True

}};

log {{
    source(s_gen);
    parser {{
        python(class("MyParser"));
    }};
    destination {{
        file("{OUTPUT_FILE_PARSER}"
             template("$ISODATE $HOST $MSGHDR$FOOBAR\\n")
        );
    }};
}};
"""

    config.set_raw_config(raw_config)
    syslog_ng.start(config)

    # Wait for messages to be processed and written
    import time
    time.sleep(2)

    # Stop syslog-ng to flush all buffers
    syslog_ng.stop()

    # Verify messages were parsed and written
    output_file = Path(OUTPUT_FILE_PARSER)
    assert output_file.exists(), \
        f"Python parser test did not create {OUTPUT_FILE_PARSER}"

    with open(output_file, 'r') as f:
        lines = f.readlines()

    assert len(lines) == NUM_MESSAGES, \
        f"Expected {NUM_MESSAGES} messages, got {len(lines)}"

    # Verify FOOBAR field contains the MSG content
    for i, line in enumerate(lines, 1):
        assert "parser test" in line, \
            f"Line {i}: FOOBAR field does not contain expected message"
