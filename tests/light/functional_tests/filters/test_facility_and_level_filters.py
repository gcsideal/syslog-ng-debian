#!/usr/bin/env python
#############################################################################
# Copyright (c) 2007-2015 Balabit
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
# Constants for test templates and filters
MSG_TEMPLATE_BASE = "Feb 11 21:27:22 testhost testprogram[9999]: "
NUM_MESSAGES = 10
FREQ_IMMEDIATE = 0

# Priority values (facility * 8 + level)
PRI_SYSLOG_ALERT = 41  # facility=5(syslog), level=1(alert)
PRI_KERN_ALERT = 1     # facility=0(kern), level=1(alert)
PRI_MAIL_ALERT = 17    # facility=2(mail), level=1(alert)
PRI_DAEMON_ALERT = 25  # facility=3(daemon), level=1(alert)
PRI_AUTH_ALERT = 33    # facility=4(auth), level=1(alert)
PRI_LPR_ALERT = 49     # facility=6(lpr), level=1(alert)
PRI_DEBUG = 7          # facility=0(kern), level=7(debug)
PRI_INFO = 6           # facility=0(kern), level=6(info)
PRI_NOTICE = 5         # facility=0(kern), level=5(notice)
PRI_WARNING = 4        # facility=0(kern), level=4(warning)
PRI_ERR = 3            # facility=0(kern), level=3(err)
PRI_CRIT = 2           # facility=0(kern), level=2(crit)
PRI_ALERT = 1          # facility=0(kern), level=1(alert)

# Filter expressions
FILTER_FACILITY_SYSLOG = "facility(syslog)"
FILTER_FACILITY_KERN = "facility(kern)"
FILTER_FACILITY_MAIL = "facility(mail)"
FILTER_FACILITY_MULTI = "facility(daemon,auth,lpr)"
FILTER_LEVEL_DEBUG = "level(debug)"
FILTER_LEVEL_INFO = "level(info)"
FILTER_LEVEL_NOTICE = "level(notice)"
FILTER_LEVEL_WARNING_TO_CRIT = "level(warning..crit)"


# Test individual facility filters (syslog, kern, mail)
#
def test_facility_single(config, syslog_ng):
    """Test filtering by single facility values."""
    # Create source with example-msg-generator
    generator_source1 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_SYSLOG_ALERT}>{MSG_TEMPLATE_BASE}facility1"),
    )
    generator_source2 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_KERN_ALERT}>{MSG_TEMPLATE_BASE}facility2"),
    )
    generator_source3 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_MAIL_ALERT}>{MSG_TEMPLATE_BASE}facility3"),
    )

    # Create destinations
    dest1 = config.create_file_destination(file_name="test-facility1.log")
    dest2 = config.create_file_destination(file_name="test-facility2.log")
    dest3 = config.create_file_destination(file_name="test-facility3.log")
    dest4 = config.create_file_destination(file_name="test-facility-combined.log")

    # Create log paths with unique parser and filter instances
    config.create_logpath(statements=[generator_source1, config.create_syslog_parser(), config.create_filter(FILTER_FACILITY_SYSLOG), dest1])
    config.create_logpath(statements=[generator_source2, config.create_syslog_parser(), config.create_filter(FILTER_FACILITY_KERN), dest2])
    config.create_logpath(statements=[generator_source3, config.create_syslog_parser(), config.create_filter(FILTER_FACILITY_MAIL), dest3])

    # Test that filter actually filters: SINGLE logpath with all 3 sources, filter for only syslog
    # Should get only the 10 messages from generator_source1, the other 20 should be filtered out
    config.create_logpath(statements=[generator_source1, generator_source2, generator_source3, config.create_syslog_parser(), config.create_filter(FILTER_FACILITY_SYSLOG), dest4])

    syslog_ng.start(config)

    logs1 = dest1.read_logs(NUM_MESSAGES)
    logs2 = dest2.read_logs(NUM_MESSAGES)
    logs3 = dest3.read_logs(NUM_MESSAGES)
    logs4 = dest4.read_logs(NUM_MESSAGES)

    assert len(logs1) == NUM_MESSAGES
    assert len(logs2) == NUM_MESSAGES
    assert len(logs3) == NUM_MESSAGES
    assert len(logs4) == NUM_MESSAGES

    assert all("facility1" in log for log in logs1)
    assert all("facility2" in log for log in logs2)
    assert all("facility3" in log for log in logs3)
    # Verify filter actually filters: should only get facility1 messages, not facility2 or facility3
    assert all("facility1" in log for log in logs4)
    assert not any("facility2" in log for log in logs4)
    assert not any("facility3" in log for log in logs4)


# Test multi-facility filter (daemon,auth,lpr)
#
def test_facility_multi(config, syslog_ng):
    """Test filtering by multiple facility values."""
    # Create sources
    generator_source1 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_DAEMON_ALERT}>{MSG_TEMPLATE_BASE}facility4"),
    )
    generator_source2 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_AUTH_ALERT}>{MSG_TEMPLATE_BASE}facility4"),
    )
    generator_source3 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_LPR_ALERT}>{MSG_TEMPLATE_BASE}facility4"),
    )

    # Create separate destination objects for each logpath (all writing to same file)
    dest4_1 = config.create_file_destination(file_name="test-facility4.log", persist_name="dest4_1")
    dest4_2 = config.create_file_destination(file_name="test-facility4.log", persist_name="dest4_2")
    dest4_3 = config.create_file_destination(file_name="test-facility4.log", persist_name="dest4_3")

    # Create log paths with unique parser and filter instances
    config.create_logpath(statements=[generator_source1, config.create_syslog_parser(), config.create_filter(FILTER_FACILITY_MULTI), dest4_1])
    config.create_logpath(statements=[generator_source2, config.create_syslog_parser(), config.create_filter(FILTER_FACILITY_MULTI), dest4_2])
    config.create_logpath(statements=[generator_source3, config.create_syslog_parser(), config.create_filter(FILTER_FACILITY_MULTI), dest4_3])

    syslog_ng.start(config)

    logs4 = dest4_1.read_logs(30)
    assert len(logs4) == 30
    assert all("facility4" in log for log in logs4)


# Test individual level filters (debug, info, notice)
#
def test_level_single(config, syslog_ng):
    """Test filtering by single level values."""
    # Create sources
    generator_source1 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_DEBUG}>{MSG_TEMPLATE_BASE}level1"),
    )
    generator_source2 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_INFO}>{MSG_TEMPLATE_BASE}level2"),
    )
    generator_source3 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_NOTICE}>{MSG_TEMPLATE_BASE}level3"),
    )

    # Create destinations
    dest1 = config.create_file_destination(file_name="test-level1.log")
    dest2 = config.create_file_destination(file_name="test-level2.log")
    dest3 = config.create_file_destination(file_name="test-level3.log")
    dest4 = config.create_file_destination(file_name="test-level-combined.log")

    # Create log paths with unique parser and filter instances
    config.create_logpath(statements=[generator_source1, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_DEBUG), dest1])
    config.create_logpath(statements=[generator_source2, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_INFO), dest2])
    config.create_logpath(statements=[generator_source3, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_NOTICE), dest3])

    # Test that filter actually filters: SINGLE logpath with all 3 sources, filter for only debug
    # Should get only the 10 messages from generator_source1, the other 20 should be filtered out
    config.create_logpath(statements=[generator_source1, generator_source2, generator_source3, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_DEBUG), dest4])

    syslog_ng.start(config)

    logs1 = dest1.read_logs(NUM_MESSAGES)
    logs2 = dest2.read_logs(NUM_MESSAGES)
    logs3 = dest3.read_logs(NUM_MESSAGES)
    logs4 = dest4.read_logs(NUM_MESSAGES)

    assert len(logs1) == NUM_MESSAGES
    assert len(logs2) == NUM_MESSAGES
    assert len(logs3) == NUM_MESSAGES
    assert len(logs4) == NUM_MESSAGES

    assert all("level1" in log for log in logs1)
    assert all("level2" in log for log in logs2)
    assert all("level3" in log for log in logs3)
    # Verify filter actually filters: should only get level1 (debug) messages, not level2 (info) or level3 (notice)
    assert all("level1" in log for log in logs4)
    assert not any("level2" in log for log in logs4)
    assert not any("level3" in log for log in logs4)


# Test level range filter (warning..crit)
#
def test_level_multi(config, syslog_ng):
    """Test filtering by level range."""
    # Create sources - messages that should match
    source_match1 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_WARNING}>{MSG_TEMPLATE_BASE}level4"),
    )
    source_match2 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_ERR}>{MSG_TEMPLATE_BASE}level4"),
    )
    source_match3 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_CRIT}>{MSG_TEMPLATE_BASE}level4"),
    )

    # Create sources - messages that should be filtered out
    source_filtered1 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_DEBUG}>{MSG_TEMPLATE_BASE}level4_filtered"),
    )
    source_filtered2 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_NOTICE}>{MSG_TEMPLATE_BASE}level4_filtered"),
    )
    source_filtered3 = config.create_example_msg_generator_source(
        num=NUM_MESSAGES, freq=FREQ_IMMEDIATE, template=config.stringify(f"<{PRI_ALERT}>{MSG_TEMPLATE_BASE}level4_filtered"),
    )

    # Create separate destination objects for each logpath (all writing to same file)
    outfile = "test-level4.log"
    dest4_1 = config.create_file_destination(file_name=outfile, persist_name="level_dest4_1")
    dest4_2 = config.create_file_destination(file_name=outfile, persist_name="level_dest4_2")
    dest4_3 = config.create_file_destination(file_name=outfile, persist_name="level_dest4_3")
    dest4_4 = config.create_file_destination(file_name=outfile, persist_name="level_dest4_4")
    dest4_5 = config.create_file_destination(file_name=outfile, persist_name="level_dest4_5")
    dest4_6 = config.create_file_destination(file_name=outfile, persist_name="level_dest4_6")

    # Create log paths with unique parser and filter instances - only matching messages should pass
    config.create_logpath(statements=[source_match1, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_WARNING_TO_CRIT), dest4_1])
    config.create_logpath(statements=[source_match2, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_WARNING_TO_CRIT), dest4_2])
    config.create_logpath(statements=[source_match3, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_WARNING_TO_CRIT), dest4_3])
    config.create_logpath(statements=[source_filtered1, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_WARNING_TO_CRIT), dest4_4])
    config.create_logpath(statements=[source_filtered2, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_WARNING_TO_CRIT), dest4_5])
    config.create_logpath(statements=[source_filtered3, config.create_syslog_parser(), config.create_filter(FILTER_LEVEL_WARNING_TO_CRIT), dest4_6])

    syslog_ng.start(config)

    # Only priorities 4, 3, 2 should match warning..crit (30 messages)
    # Priorities 7 (debug), 5 (notice), 1 (alert) should be filtered out (30 messages filtered)
    logs4 = dest4_1.read_logs(NUM_MESSAGES * 3)
    assert len(logs4) == NUM_MESSAGES * 3
    assert all("level4" in log for log in logs4)
    assert not any("level4_filtered" in log for log in logs4)
