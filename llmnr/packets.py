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

import socket, struct
from .queries import query_aton, query_ntoa
LLMNR_addrs = { socket.AF_INET : '224.0.0.252',
                socket.AF_INET6 : 'ff02:0:0:0:0:0:1:3'}
LLMNR_PORT = 5355

# Uses utf-8 encoding for all strings.  RFC 4795 does not specify an
# encoding.  Microsoft says we MUST use utf-8.
# https://tools.ietf.org/html/rfc4795
# http://download.microsoft.com/download/9/5/E/.../%5BMS-LLMNRP%5D.pdf 

class Question:
    """A DNS question. Initialize with a bytearray in DNS format or a
    string in dotted hostname format.  The optional keyword arguments
    can be used to specify class and type when initializing from a
    string.

    The bytearray may contain additional records preceding or
    following the question. The offset argument determines the
    start of the question data.  The data may be compressed, in
    which case the pointers will be resolved from the beginning of the
    data.  Thus when unpacking data read from a socket, the entire
    received string should be passed as data.

    The length of a Question is the length of the compressed
    data string, so the offset to the next resource record is
    offset + len(question).

    NOTE: An LLMNR sender SHOULD send only single-label names in A and
    AAAA queries.

    """
    def __init__(self, data, offset=0, qtype='A', CLASS=1):
        if isinstance(data, str):
            self.labels = data.split('.')
            self.TYPE, self.CLASS = query_aton[qtype], CLASS
            self._length = 0
        elif isinstance(data, bytearray):
            N, self.labels, saved = offset, [], None
            while data[N] != 0:
                if data[N] & 0xc0 == 0xc0:
                    saved, N = N+1, 0x3f&struct.unpack('!H', data[N:N+2])[0]
                self.labels.append(str(data[N+1:N+1+data[N]].decode('utf-8')))
                N = N+1+data[N]
            if saved is not None:
                N = saved
            N += 1
            self.TYPE, self.CLASS = struct.unpack('!HH', data[N:N+4])
            self._length = N + 4 - offset
        else:
            raise ValueError('Instantiate a Question with a bytearray or str')

    def __len__(self):
        return self._length

    def __repr__(self):
        return 'Question: TYPE=%s CLASS=%s NAME=%s'%(
            self.TYPE, self.CLASS, self.name())

    def name(self):
        """Return the name field of this question, in dotted string format.

        """
        return '.'.join(self.labels)

    def qtype(self):
        """Return the type of this question in alphabetical form."""
        return query_ntoa[self.TYPE]

    def bytes(self):
        result = bytearray()
        for label in self.labels:
            result.append(len(label))
            result += bytearray(label, 'utf-8')
        result += struct.pack('!BHH', 0, self.TYPE, self.CLASS)
        return result

class ResourceRecord(Question):
    """A DNS Resource Record, for use in any of the three answer sections
    of an LLMNR response packet.  The structure is the same as that of
    a question, but extended by the fields TTL, RDLENGTH and RDATA.

    """
    def __init__(self, data, offset=0, qtype='A', CLASS=1, TTL=30,
                 rdata=bytearray()):
        Question.__init__(self, data, offset, qtype, CLASS)
        if isinstance(data, str):
            self.TTL = TTL
            self.RDATA = bytearray(rdata)
            self.RDLENGTH = len(self.RDATA)
        else:
            # This does not deal with compressed RDATA
            N = offset + self._length
            self.TTL, self.RDLENGTH = struct.unpack('!LH', data[N:N+6])
            N += 6
            self.RDATA = data[N:N+self.RDLENGTH]
        self._length += (6 + self.RDLENGTH)

    def __repr__(self):
        return 'Record: TYPE=%s CLASS=%s NAME=%s TTL=%s data:%s'%(
            self.TYPE, self.CLASS, '.'.join(self.labels), self.TTL,
            repr(self.RDATA))

    def bytes(self):
        result = bytearray()
        for label in self.labels:
            result.append(len(label))
            result += bytearray(label, 'utf-8')
        result += struct.pack('!BHHLH', 0, self.TYPE, self.CLASS,
                              self.TTL, self.RDLENGTH)
        result += self.RDATA
        return result
    
class Packet(object):
    """An LLMNR packet. Instantiate with a bytearray of data.  If
    no data is provided, the packet will have all fields set to 0.

    >>> header = bytearray('\x00\x23\x80\x00\x00\x01\x00\x00\x00\x00\x00\x00')
    >>> len(header)
    12
    >>> q = llmnr.Question('aa.bb.cc')
    >>> data = header + q.to_bytes()
    >>> p = llmnr.Packet(data)
    >>> p
    LLMNR packet #35
    >>> p.questions
    [Question: TYPE=1 CLASS=1 NAME=aa.bb.cc]

    """
    hdr = '!HBBHHHH'
    def __init__(self, data=bytearray([0]*12)):
        header = struct.unpack(self.hdr, data[:12])
        self.ID, self.flags, code, QD, AN, NS, AR = header
        self.RCODE = code&0xf
        N = 12
        self.questions = []
        for n in range(QD):
            Q = Question(data, offset=N)
            self.questions.append(Q)
            N += len(Q)
        self.answers = []
        for n in range(AN):
            A = ResourceRecord(data, offset=N)
            self.answers.append(A)
            N += len(A)
        self.nameservers = []
        for n in range(NS):
            S = ResourceRecord(data, offset=N)
            self.nameservers.append(S)
            N += len(A)
        self.additional = []
        for n in range(AR):
            R = ResourceRecord(data, offset=N)
            self.additional.append(R)
            N += len(R)

    def __repr__(self):
        return 'LLMNR packet #%d'%self.ID

    def _set_field(self, mask, value):
        bits = mask | value if value else 0
        self.flags = (self.flags&~mask) | bits
    def _set_bit(self, mask, value):
        bit = mask if value else 0
        self.flags = (self.flags&~mask) | bit
    @property
    def QR(self):
        """True for response, False for query."""
        return self.flags&0x80 != 0
    @QR.setter
    def QR(self, value):
        self._set_bit(0x80, value)
    @property
    def OPCODE(self):
        """As of RFC4795 only 0 is supported."""
        return self.flags&0x78 >> 3
    @OPCODE.setter
    def OPCODE(self, code):
        self._set_field(0x78, code&0xf << 3)
    @property
    def C(self):
        """A name conflict has been detected."""
        return self.flags&0x4 != 0
    @C.setter
    def C(self, value):
        self._set_bit(0x4, value)
    @property
    def TC(self):
        """Packet has been truncated."""
        return self.flags&0x2 != 0
    @TC.setter
    def TC(self, value):
        self._set_bit(0x2, value)
    @property
    def T(self):
        """This is a tentative response."""
        return self.flags&0x1 != 0
    @T.setter
    def T(self, value):
        self._set_bit(0x1), value
    @property
    def QDCOUNT(self):
        return len(self.questions)
    @property
    def ANCOUNT(self):
        return len(self.answers)
    @property
    def NSCOUNT(self):
        return len(self.nameservers)
    @property
    def ARCOUNT(self):
        return len(self.additional)

    def bytes(self):
        """Return a bytearray representing this packet."""
        result = bytearray(struct.pack('!HBBHHHH',
                           self.ID, self.flags, self.RCODE,
                           self.QDCOUNT, self.ANCOUNT,
                           self.NSCOUNT, self.ARCOUNT))
        for question in self.questions:
            result += question.bytes()
        for answer in self.answers:
            result += answer.bytes()
        for server in self.nameservers:
            result += server.bytes()
        for record in self.additional:
            result += record.bytes()
        return result

