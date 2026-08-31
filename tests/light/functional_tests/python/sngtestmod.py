#############################################################################
# Copyright (c) 2015 Balabit
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
from syslogng import LogDestination


class DestTest(LogDestination):

    def init(self, options):
        return True

    def deinit(self):
        pass

    def open(self):
        return True

    def close(self):
        pass

    def is_open(self):
        return True

    def send(self, msg):
        with open('test-python.log', 'a') as f:
            # Convert bytes to strings and handle missing fields
            msg_dict = {
                key: (value.decode() if isinstance(value, bytes) else value)
                for key, value in msg.items()
            }

            # Get values with defaults for missing fields
            date = msg_dict.get('DATE', '')
            host = msg_dict.get('HOST', '')
            msghdr = msg_dict.get('MSGHDR', '')
            message = msg_dict.get('MSG', '')

            f.write(f'{date} {host} {msghdr}{message}\n')

        return True
