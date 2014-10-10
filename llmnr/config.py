# -*- coding: utf-8 -*-
# Copyright© 2014 by Marc Culler and others.
#
# This file is part of Llamar.
#
# Llamar is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Llamar is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with QuerierD.  If not, see <http://www.gnu.org/licenses/>.
#
# References:
# https://tools.ietf.org/html/rfc4795
# http://msdn.microsoft.com/en-us/library/dd240328.aspx

from configparser import ConfigParser, NoSectionError, NoOptionError
from .iproute import NetworkState
import os, socket

CONFIG_FILE = '/etc/llmnr.conf'

class Config(ConfigParser):
    """An object which plays the role for LLMNR of a DNS database.

    Provides methods get_address and get_name, which map hostnames to
    addresses, or addresses to hostnames.  The mappings are determined
    by a config file which is read and parsed when the object is
    instantiated.

    """
    def __init__(self, config_file=CONFIG_FILE):
        if not os.path.exists(config_file):
            raise ValueError('Please create the config file %s.'%config_file)
        ConfigParser.__init__(self)
        self.read(config_file)
        self.network = NetworkState()

    def current_addresses(self):
        self.network.update()
        result = {'inet':[], 'inet6':[]}
        for link in self.network.links:
            if link.state != 'UP' or link.name not in self.sections():
                continue
            address = link.primary_address('inet')
            if address:
                result['inet'].append(address.string())
            address = link.primary_address('inet6')
            if address:
                result['inet6'].append(address.string()+'%'+link.name)
        return result

    def get_address(self, hostname, address_family):
        """Return the primary address assigned to a hostname.  Supported
        address families are 'inet' and 'inet6'.

        """
        self.network.update()
        links = dict((link.name, link) for link in self.network.links)
        for section in self.sections():
            if section in links:
                link = links[section]
            else:
                continue
            try:
                config_name = self.get(section, 'name')
            except NoOptionError:
                config_name = os.uname()[1].split('.')[0].lower()
            # By default, option names are converted to lower case.
            if link.state == 'UP' and hostname.lower() == config_name:
                address = link.primary_address(address_family)
                if address:
                    return address
                else:
                    continue
        return None

    def get_name(self, address):
        """Return the hostname assigned to an address.  The address should be
        given as a string.  The family is detected from the string.

        """
        try:
            addr = socket.inet_pton(socket.AF_INET, address)
            addr_family = socket.AF_INET
            addr_type = 'inet'
        except (socket.error, ValueError):
            try:
                addr = socket.inet_pton(socket.AF_INET6, address)
                addr_family = socket.AF_INET6
                addr_type = 'inet6'
            except (socket.error, ValueError):
                return
        for link in self.network.links:
            link_addr = link.primary_address(addr_type)
            if link_addr is None:
                continue
            if addr == socket.inet_pton(addr_family, link_addr.string()):
                try:
                    return self.get(link.name, 'name')
                except NoOptionError:
                    return os.uname()[1].split('.')[0].lower()
