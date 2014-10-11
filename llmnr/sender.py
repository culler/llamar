# -*- coding: utf-8 -*-
# Copyright© 2014 by Marc Culler and others.
#
# This file is part of LLamar.
#
# LLamar is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# LLamar is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LLamar.  If not, see <http://www.gnu.org/licenses/>.
#
# References:
# https://tools.ietf.org/html/rfc4795
# http://msdn.microsoft.com/en-us/library/dd240328.aspx

import socket, struct, time
from random import random
from .queries import query_ntoa
from .packets import Packet, Question, ResourceRecord, LLMNR_addrs, LLMNR_PORT
from .iproute import NetworkState

class Sender(object):
    """Object with an ask method which sends LLMNR queries of type A,
    AAAA, PTR or * and returns the result as a list of tuples.

    The iface and family options pertain to UDP multicast queries.

    """
    JITTER_INTERVAL = 0.1
    LLMNR_TIMEOUT = 1.0
    UDP_SOCKET_TIMEOUT = 0.2

    def __init__(self, iface=None, family='inet'):
        self.ID = 1
        self.family = family
        if family == 'inet':
            self.AF = socket.AF_INET
            self.IPPROTO = socket.IPPROTO_IP
            self.LOOP = socket.IP_MULTICAST_LOOP
        elif family == 'inet6':
            self.AF = socket.AF_INET6
            self.IPPROTO = socket.IPPROTO_IPV6
            self.LOOP = socket.IPV6_MULTICAST_LOOP
        else:
            raise ValueError('family should be inet or inet6.')
        if iface == None:
            self.address = ''
        else:
            try:
                ns = NetworkState()
                link = ns[iface]
                if link.state != 'UP':
                    raise ValueError('Requested interface is not up.')
            except KeyError:
                raise ValueError('Unknown interface.')
            self.address = link.addresses[family]

    def ask(self, hostname, qtype='A', server=None, wait=False):
        """Send an LLMNR query of specified type (A, AAAA or PTR).  If a
        server address is specified the request will be sent using
        unicast TCP.  Otherwise the request will be multicast UDP.
        
        RFC 4795 says we "MAY send multicast UDP queries for PTR RRs."
        Microsoft says we SHOULD use UDP multicast."

        """
        if qtype=='PTR':
            if hostname.split('.')[-1] != 'arpa':
                hostname = self._to_arpa(hostname)
                if not hostname:
                    return
        if server is None: # We are using multicast UDP
            query_socket = socket.socket(self.AF,
                                         socket.SOCK_DGRAM,
                                         socket.IPPROTO_UDP)
            query_socket.setsockopt(self.IPPROTO, self.LOOP, 1)
            query_socket.bind((self.address, 0))
        else: # We are using unicast TCP
            sockaddr = self._server_sockaddr(server)
            if sockaddr:
                query_socket = socket.socket(self._AF(server),
                                             socket.SOCK_STREAM)
                query_socket.bind(sockaddr)
            else:
                print('Failed to open TCP socket')
                return
        query = Packet()
        query.ID = self.ID
        self.ID += 1
        question = Question(hostname, qtype=qtype)
        query.questions.append(question)
        if server is None:  # normal UDP conversation
            for n in range(3):
                responses = self._UDP_communicate(query, query_socket)
                if responses:
                    break
            if not wait:
                query_socket.close()
            else:
                # Keep listening for more responses.
                query_socket.close()
            if [packet for packet, sender in responses if packet.C]:
                return self._handle_conflict(responses)
            for packet, sender in responses:
                # Who knows what it means if only some responses are truncated.
                if packet.TC and len(responses) == 1:
                    return self.ask(hostname, qtype, sender[0])
            packets = [packet for packet, sender in responses]
        else: # send a query by TCP
            packets = [self._TCP_communicate(query, query_socket, server)]
        if not packets:
            return
        result = []
        for packet in packets:
            for answer in packet.answers:
                data = bytes(answer.RDATA)
                qtype = query_ntoa[answer.TYPE]
                if qtype == 'A':
                    rr = socket.inet_ntop(socket.AF_INET, data)
                elif qtype == 'AAAA':
                    rr = socket.inet_ntop(socket.AF_INET6, data)
                elif qtype == 'PTR':
                    rr = self._dns_to_dotted(answer.RDATA)
                else:
                    rr = answer.RDATA
                result.append((qtype, rr))
        return result

    def _handle_conflict(self, responses):
        print('Conflict detected!')

    def _delay(self):
        """Sleep for a random time interval between 0 and JITTER_INTERVAL.

        RFC 4795 says each query transmission SHOULD be delayed like this.
        Microsoft says they SHOULD NOT be delayed. 
        """
        time.sleep(self.JITTER_INTERVAL*random())

    def _dns_to_dotted(self, data):
        """Return a name as a dotted-quad string.
        
        RFC 4795 does not specify an encoding.  Microsoft says we MUST
        use utf-8.

        """
        N, labels = 0, []
        while data[N] != 0:
            labels.append(str(data[N+1:N+1+data[N]].decode('utf-8')))
            N += 1 + data[N]
        return '.'.join(labels)

    def _UDP_communicate(self, query, query_socket):
        timeout = self.UDP_SOCKET_TIMEOUT
        query_socket.settimeout(timeout)
        self._delay()
        query_socket.sendto(query.bytes(), (LLMNR_addrs[self.AF], LLMNR_PORT) )
        responses = []
        self._collect_UDP_responses(query_socket, responses)
        return responses

    def _collect_UDP_responses(self, query_socket, response_list):
        start = time.time()
        timeout = self.LLMNR_TIMEOUT+self.JITTER_INTERVAL
        while True:
            try:
                received, sender = query_socket.recvfrom(8192)
            except socket.timeout:
                if time.time() - start > timeout:
                    break
                else:
                    continue
            try:
                packet = Packet(bytearray(received))
                response_list.append( (packet, sender) )
                if len(response_list) == 1 and not packet.C:
                    return
            except:
                print('Bad packet!')
                print(received)
                
    def _TCP_communicate(self, query, query_socket, server):
        server_AF = self._AF(server)
        query_socket.settimeout(1.0)
        try:
            sockaddr = socket.getaddrinfo(
                server, LLMNR_PORT, server_AF,
                socket.SOCK_STREAM, socket.SOL_TCP)[0][-1]
            query_socket.connect(sockaddr)
            data = query.bytes()
            self._delay()
            sent = 0
            while sent < len(data):
                sent += query_socket.send(data[sent:])
            # This sends a FIN
            query_socket.shutdown(socket.SHUT_WR)
            received = bytes()
            while True:
                data = query_socket.recv(8192)
                if not data:
                    break
                received += data
            query_socket.close()
        except socket.error as e:
            if str(e) != 'timed out':
                print('TCP query failed: %s'%e)
            query_socket.close()
            return
        try:
            return Packet(bytearray(received))
        except:
            print('Bad packet!')
            print(received)

    def _server_sockaddr(self, server):
        server_AF = self._AF(server)
        if server_AF == socket.AF_INET:
            return ('', 0)
        else:
            ns = NetworkState()
            addr = None
            for link in ns.links:
                state = link.state
                ip6 = link.primary_address('inet6')
                if state=='UP' and ip6 is not None:
                    addr = '%s%%%s'%(ip6.string(), link.name)
                    break
            if addr is None:
                print('No IPv6 interface available')
                return None
            try:
                return socket.getaddrinfo(
                    addr, 0, server_AF,
                    socket.SOCK_STREAM, socket.SOL_TCP)[0][-1]
            except socket.error as e:
                print(e)
                return None

    def _AF(self, address):
        """Return the appropriate AF_* socket option for this address."""
        try:
            socket.inet_aton(address)  # fails unless server address is IPv4 
            return socket.AF_INET
        except socket.error:
            return socket.AF_INET6

    def _to_arpa(self, address):
        """Construct the .arpa name for an address in string form."""
        try:
            addr = socket.inet_pton(socket.AF_INET, address)
            labels = address.split('.')
            labels.reverse()
            labels += ['in-addr', 'arpa']
            return '.'.join(labels)
        except (socket.error, ValueError):
            pass
        try:
            packed = bytearray(socket.inet_pton(socket.AF_INET6, address))
            labels = list(''.join(['%.2x'%b for b in packed]))
            labels.reverse()
            labels += ['ip6', 'arpa']
            return '.'.join(labels)
        except (socket.error, ValueError):
            pass
            
