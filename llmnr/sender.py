import socket, struct, time
from random import random
from .queries import query_ntoa
from .packets import Packet, Question, ResourceRecord, LLMNR_addrs, LLMNR_PORT
from .iproute import NetworkState

# https://tools.ietf.org/html/rfc4795
# http://download.microsoft.com/download/9/5/E/.../%5BMS-LLMNRP%5D.pdf 

class Sender(object):
    """Object with an ask method which sends LLMNR queries of type A,
    AAAA, PTR or * and returns the result as a list of tuples.

    The iface and family options pertain to UDP multicast queries.

    """
    JITTER_INTERVAL = 0.1

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

    def _delay(self):
        """Sleep for a random time interval between 0 and JITTER_INTERVAL.

        RFC 4795 says each query transmission SHOULD be delayed like this.
        Microsoft says they SHOULD NOT be delayed. 
        """
        time.sleep(self.JITTER_INTERVAL*random())

    def ask(self, hostname, qtype='A', server=None):
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
        response = None
        if server is None:
            response = self._UDP_communicate(query, query_socket)
        else:
            response = self._TCP_communicate(query, query_socket, server)
        query_socket.close()
        if response:
            result = []
            for answer in response.answers:
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
        timeout = 0.2
        query_socket.settimeout(timeout)
        query_socket.sendto(query.bytes(),
                            (LLMNR_addrs[self.AF], LLMNR_PORT) )
        for n in range(3):
            try:
                self._delay()
                received = query_socket.recv(8192)
                try:
                    # We should check the TC flag.  If set, resend the
                    # query over TCP.
                    # If the C flag is set, we are supposed to collect
                    # responses and concatenate them.
                    return Packet(bytearray(received))
                except:
                    print('Bad packet!')
                    print(received)
                    return
            except socket.timeout:
                timeout *= 2
                query_socket.settimeout(timeout)
                continue
            break

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
        except socket.error as e:
            if str(e) != 'timed out':
                print('TCP query failed: %s'%e)
            return
        received = bytes()
        while True:
            data = query_socket.recv(8192)
            if not data:
                break
            received += data
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
            
