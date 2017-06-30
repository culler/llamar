# -*- coding: utf-8 -*-
# Copyright© 2014-2017 by Marc Culler and others.
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

query_pairs = [
(1, 'A'),
(2, 'NS'),
(3, 'MD'),
(4, 'MF'),
(5, 'CNAME'),
(6, 'SOA'),
(7, 'MB'),
(8, 'MG'),
(9, 'MR'),
(10, 'NULL'),
(11, 'WKS'),
(12, 'PTR'),
(13, 'HINFO'),
(14, 'MINFO'),
(15, 'MX'),
(16, 'TXT'),
(17, 'RP'),
(18, 'AFSDB'),
(19, 'X25'),
(20, 'ISDN'),
(21, 'RT'),
(22, 'NSAP'),
(23, 'NSAP-PTR'),
(24, 'SIG'),
(25, 'KEY'),
(26, 'PX'),
(27, 'GPOS'),
(28, 'AAAA'),
(29, 'LOC'),
(30, 'NXT'),
(31, 'EID'),
(32, 'NIMLOC'),
(33, 'SRV'),
(34, 'ATMA'),
(35, 'NAPTR'),
(36, 'KX'),
(37, 'CERT'),
(38, 'A6'),
(39, 'DNAME'),
(40, 'SINK'),
(41, 'OPT'),
(42, 'APL'),
(43, 'DS'),
(44, 'SSHFP'),
(45, 'IPSECKEY'),
(46, 'RRSIG'),
(47, 'NSEC'),
(48, 'DNSKEY'),
(49, 'DHCID'),
(50, 'NSEC3'),
(51, 'NSEC3PARAM'),
(52, 'TLSA'),
(55, 'HIP'),
(56, 'NINFO'),
(57, 'RKEY'),
(58, 'TALINK'),
(59, 'CDS'),
(60, 'CDNSKEY'),
(61, 'OPENPGPKEY'),
(99, 'SPF'),
(100, 'UINFO'),
(101, 'UID'),
(102, 'GID'),
(103, 'UNSPEC'),
(104, 'NID'),
(105, 'L32'),
(106, 'L64'),
(107, 'LP'),
(108, 'EUI48'),
(109, 'EUI64'),
(249, 'TKEY'),
(250, 'TSIG'),
(251, 'IXFR'),
(252, 'AXFR'),
(253, 'MAILB'),
(254, 'MAILA'),
(255, '*'),
(256, 'URI'),
(257, 'CAA'),
(32768, 'TA'),
(32769, 'DLV')
]
query_ntoa = dict(query_pairs)
query_aton = dict((y,x) for x, y in query_pairs)
