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

from subprocess import Popen, PIPE

address_types = ['link/ether', 'link/loopback', 'inet', 'inet6']

class Address:
    """An address associated to a network link."""

    def __init__(self, addrinfo):
        self.info = addrinfo
        self.__dict__.update(addrinfo)
    
    def __repr__(self):
        return self.value

    def string(self):
        return self.value.split('/')[0]

class Link:
    """A network link."""

    def __init__(self, linkinfo):
        addrs = [Address(a) for a in linkinfo.get('addresses', [])]
        self.__dict__.update(linkinfo)
        self.addresses = {}
        for atype in address_types:
            self.addresses[atype] = [a for a in addrs if a.type == atype]
        self.mtu = int(self.mtu)
        try:
            self.qlen = int(self.qlen)
        except AttributeError:
            pass

    def __repr__(self):
        return self.name

    def primary_address(self, atype):
        addresses = self.addresses[atype]
        if len(addresses) > 0:
            return addresses[0]
        else:
            return None

class NetworkState:
    """A snapshot of currently available network links."""

    def __init__(self):
        self.update()

    def __getitem__(self, key):
        return self._info[key]

    def _words(self, line, sep=None):
        return [word.strip() for word in line.split(sep)]

    def _dict_split(self, wordlist):
        return dict(list(zip(wordlist[0::2],wordlist[1::2])))

    @property
    def links(self):
        return list(self._info.values())

    def labels(self):
        inet_addrs = []
        for l in self.links:
            inet_addrs += l.addresses['inet']
        return list(set([a.label for a in inet_addrs]))

    def update(self):
        ip = Popen(['ip', 'address'], stdin=PIPE, stdout=PIPE)
        output, error = ip.communicate()
        output = str(output, encoding='ascii')
        lines = [line.strip() for line in output.split('\n')]
        links = {}
        while lines:
            line = lines.pop(0)
            if len(line) == 0:
                continue
            if line[0].isdigit():
                newlink = {}
                index, name, info = self._words(line, ':')
                links[name] = newlink
                newlink['name']=name
                info = self._words(info)
                newlink['flags'] = info.pop(0)
                newlink.update(self._dict_split(info))
            else:
                info = self._words(line)
                if info[0] in address_types:
                    newaddr = {'type':info.pop(0), 'value':info.pop(0)}
                    try:
                        newlink['addresses'].append(newaddr)
                    except KeyError:
                        newlink['addresses'] = [newaddr]
                    if newaddr['type'] == 'inet':
                        newaddr['label'] = info.pop()
                    if 'secondary' in info:
                        info.remove('secondary')
                        newaddr['secondary'] = True
                    else:
                        newaddr['secondary'] = False
                newaddr.update(self._dict_split(info))
        self._info = dict( (l, Link(links[l])) for l in links )
