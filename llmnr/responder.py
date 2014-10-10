import socket, struct, select, time
from random import random
from .queries import query_ntoa, query_aton
from .sender import Sender
from .packets import Packet, ResourceRecord, LLMNR_addrs, LLMNR_PORT
from .config import Config, NoSectionError
from .iproute import NetworkState
IP_PKTINFO=8

# https://tools.ietf.org/html/rfc4795
# http://download.microsoft.com/download/9/5/E/.../%5BMS-LLMNRP%5D.pdf 

class Responder(object):
    """Simple LLMNR responder that answers A, AAAA and PTR queries.

    """
    JITTER_INTERVAL = 0.1

    def __init__(self, ttl=30):
        self.ttl = ttl
        self.config = Config()
        self.UDP_sockets = {}
        self.TCP_listeners = {}
        self._update_sockets()

    def __del__(self):
        for sock in self.UDP_sockets.keys() | self.TCP_listeners.keys():
            try:
                sock.close()
            except:
                pass

    def _delay(self):
        """Sleep for a random time interval between 0 and JITTER_INTERVAL.

        RFC 4795 says each query transmission SHOULD be delayed like this.
        Microsoft says they SHOULD NOT be delayed. 
        """
        time.sleep(self.JITTER_INTERVAL*random())

    def _update_sockets(self):
        """Make sockets consistent with the current network state."""
        self.current_addresses = current = self.config.current_addresses()
        self.packed_addresses = (
            [socket.inet_pton(socket.AF_INET, a)
             for a in current['inet'] ] +
            [socket.inet_pton(socket.AF_INET6, a.split('%')[0])
             for a in current['inet6'] ])
        self.all_addresses = current['inet'] + current['inet6']
        self._update_UDP_sockets()
        self._update_TCP_listeners()

    def _create_UDP_socket(self, family, address):
        AF = socket.AF_INET if family=='inet' else socket.AF_INET6
        try:
            udpsocket = socket.socket(AF,
                                      socket.SOCK_DGRAM,
                                      socket.IPPROTO_UDP)
            udpsocket.setsockopt(socket.SOL_SOCKET,
                                 socket.SO_REUSEADDR,
                                 1)
            udpsocket.bind( ('', LLMNR_PORT) )
            group = LLMNR_addrs[AF]
            if family == 'inet':
                udpsocket.setsockopt(socket.SOL_IP,
                                     IP_PKTINFO,
                                     1)
                membership_request = struct.pack('!4sl',
                                                 socket.inet_aton(group),
                                                 socket.INADDR_ANY)
                udpsocket.setsockopt(socket.IPPROTO_IP,
                                     socket.IP_ADD_MEMBERSHIP,
                                     membership_request)
            else:
                udpsocket.setsockopt(socket.IPPROTO_IPV6,
                                     socket.IPV6_RECVPKTINFO,
                                     1)
                membership_request = struct.pack('!16sI',
                                                 socket.inet_pton(AF, group),
                                                 socket.INADDR_ANY)
                udpsocket.setsockopt(socket.IPPROTO_IPV6,
                                     socket.IPV6_JOIN_GROUP,
                                     membership_request)
            return udpsocket
        except socket.error as e:
            if udpsocket != None:
                udpsocket.close()
            print(e)
            
    def _update_UDP_sockets(self):
        """Make sure we have a UDP socket for each configured address."""
        for udpsocket in self.UDP_sockets:
            if self.UDP_sockets[udpsocket] not in self.all_addresses:
                self.UDP_sockets.pop(udpsocket).close()
        for family in self.current_addresses:
            for address in self.current_addresses[family]:
                if address not in self.UDP_sockets.values():
                    udpsocket = self._create_UDP_socket(family, address)
                    if udpsocket:
                        self.UDP_sockets[udpsocket] = address
                        print('UDP socket at %s'%address)

    def _create_TCP_listener(self, family, address):
        AF = socket.AF_INET if family=='inet' else socket.AF_INET6
        try:
            sockaddr = socket.getaddrinfo(
                address, LLMNR_PORT, AF,
                socket.SOCK_STREAM, socket.SOL_TCP)[0][-1]
        except socket.gaierror as e:
            print(e)
            return None
        try:
            tcpsocket = socket.socket(AF, socket.SOCK_STREAM)
            tcpsocket.setsockopt(socket.SOL_SOCKET,
                                 socket.SO_REUSEADDR,
                                 1)
            # Hop count must be 1 to prevent responses
            # from leaking out of the local network.
            tcpsocket.setsockopt(socket.IPPROTO_IP,
                                 socket.IP_TTL,
                                 1)
            tcpsocket.bind(sockaddr)
            tcpsocket.listen(5)
            return tcpsocket
        except socket.error as e:
            if tcpsocket != None:
                tcpsocket.close()
            print(e)

    def _update_TCP_listeners(self):
        """Make sure we have a TCP listener for each configured address.

        RFC 4795 says that a responder MUST support UDP and TCP queries.
        Microsoft says it MUST support UDP and MAY support TCP.
        """
        for listener in self.TCP_listeners:
            if self.TCP_listeners[listener] not in self.all_addresses:
                self.TCP_listeners.pop(listener).close()
        for family in self.current_addresses:
            for address in self.current_addresses[family]:
                if address not in self.TCP_listeners.values():
                    listener = self._create_TCP_listener(family, address)
                    if listener:
                        self.TCP_listeners[listener] = address
                        print('TCP listener at %s'%address)

    def _query_is_valid(self, packet):
        """Is this a query packet that deserves a response?"""
        if ( packet.QR == True or
             packet.OPCODE != 0 or
             packet.QDCOUNT != 1 or
             packet.ANCOUNT != 0 or
             packet.NSCOUNT != 0 ):
            return False
        return True

    def _response_from_query(self, query, answers, ttl=30):
        """Convert a query packet into a response packet."""
        for qtype, answer in answers:
            data = query.questions[0].bytes()
            data += (struct.pack('!LH', ttl, len(answer)) + answer)
            record = ResourceRecord(data)
            record.TYPE = query_aton[qtype]
            query.answers.append(record)
        query.QR = True
        # set other flags according to state
        return query

    def _dots_to_dns(self, name):
        """Convert dotted quad names to DNS 'wire format'.
        
        RFC 4795 does not specify an encoding.  Microsoft says we MUST
        use utf-8.
        """
        result = bytearray()
        labels = name.split('.')
        for label in labels:
            result.append(len(label))
            result += bytearray(label, 'utf-8')
        result += bytearray(b'\0')
        return result

    def _is_datagram(self, sock):
        sock_type = sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
        return sock_type == socket.SOCK_DGRAM

    def _is_multicast(self, pktinfo):
        cmsg_level, cmsg_type, cmsg_data = pktinfo
        if cmsg_level == socket.IPPROTO_IP:
            if_index, local, dest = struct.unpack('I4s4s', cmsg_data)
            AF = socket.AF_INET
        elif cmsg_level == socket.IPPROTO_IPV6:
            dest, if_index = struct.unpack('16sI', cmsg_data)
            AF = socket.AF_INET6
        else:
            return False
        return socket.inet_pton(AF, LLMNR_addrs[AF]) == dest

    def run(self):
        """Listen for Multicast UDP queries on the LLMNR port and TCP queries
        on the LLMNR port of each configured address.  Respond to the
        sender's port if we receive a valid query for which an answer was
        specified in the config file.

        """
        while True:
            # Wait for a query to arrive
            read, write, exceptions = select.select(
                list( self.UDP_sockets.keys() | self.TCP_listeners.keys() ),
                [], [])
            active_socket = read[0]
            # Receive the query packet
            if self._is_datagram(active_socket):
                received, info, flags, sender = active_socket.recvmsg(
                    9194, 256)
                if info:
                    if not self._is_multicast(info[0]):
                        # "Unicast UDP queries MUST be silently discarded."
                        print('Ignored unicast UDP query from ', sender)
                        try:
                            P = Packet(bytearray(received))
                            print(P.questions[0])
                        except:
                            pass
                        continue
            else:
                connection, sender = active_socket.accept()
                received = bytes()
                while True:
                    data = connection.recv(8192)
                    if not data:
                        break
                    received += data
            try:
                query = Packet(bytearray(received))
            except:
                print('Bad packet from ', sender)
                continue
            # Construct an answer, if the query is valid.
            if self._query_is_valid(query):
                Q = query.questions[0]
                qtype, qname = Q.qtype(), Q.name().lower()
                print( '%s query from %s for %s'%(qtype, sender, qname) )
                answers = []
                if qtype == 'A' or qtype == '*':
                    try:
                        address = self.config.get_address(qname, 'inet')
                        ip, net = address.info['value'].split('/')
                    except (NoSectionError, AttributeError):
                        continue
                    answers.append(
                        ('A', socket.inet_pton(socket.AF_INET, ip)) )
                if qtype == 'AAAA' or qtype == '*':
                    try:
                        address = self.config.get_address(qname, 'inet6')
                        ip, net = address.info['value'].split('/')
                    except (NoSectionError, AttributeError):
                        continue
                    answers.append(
                        ('AAAA', socket.inet_pton(socket.AF_INET6, ip)) )
                if qtype == 'PTR':
                    labels = qname.split('.')
                    if labels[-1] != 'arpa':
                        continue
                    if labels[-2] == 'in-addr':
                        octets = labels[:-2]
                        octets.reverse()
                        address = '.'.join(octets)
                    elif labels[-2] == 'ip6':
                        nibbles = labels[:-2]
                        nibbles.reverse()
                        shorts = [int('0x' + ''.join(nibbles[n:n+4]), 16)
                                  for n in range(0,32,4)]
                        packed = struct.pack('!HHHHHHHH', *shorts)
                        address = socket.inet_ntop(socket.AF_INET6, packed)
                    else:
                        continue
                    if address not in self.packed_addresses:
                        continue
                    # Note: this will return lower case names only.
                    try:
                        name = self._dots_to_dns(self.config.get_name(address))
                        answers.append( ('PTR', name) )
                    except:
                        continue
                    # RFC 4795 says "If a responder is authoritative
                    # for a name, it MUST respond with RCODE=0 and an
                    # empty answer section, if the type of query does
                    # not match an RR that the responder has."
                    #
                    # Microsoft says the "responder MUST respond to
                    # queries for resource record types of A, AAAA,
                    # PTR, and ANY. The LLMNR profile responder MAY
                    # respond to queries for other resource record
                    # types, but instead SHOULD silently discard
                    # queries for other resource record types. In
                    # response to a query with resource record type of
                    # ANY, the LLMNR profile responder MUST return any
                    # eligible A and AAAA resource records."
                    #
                    # Here we go with Microsoft.

                if qtype not in ('A', 'AAAA', 'PTR', '*'):
                    continue
                # Send a response
                print( 'responding' )
                response = self._response_from_query(query, answers)
                self._delay()
                try:
                    if self._is_datagram(active_socket):
                        active_socket.sendto(response.bytes(), sender)
                    else:
                        data = response.bytes()
                        sent = 0
                        while sent < len(data):
                            sent += connection.send(data[sent:])
                        # This sends a FIN
                        connection.shutdown(socket.SHUT_WR)
                        # The socket will be closed when garbage collected.
                except socket.error as e:
                    print(e)
