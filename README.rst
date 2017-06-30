.. |copy| unicode:: 0xA9 .. copyright sign

Llamar
======

Copyright |copy| 2017, Marc Culler

Description
-----------

LLamar is a "pure" Python 3 implementation of Microsoft's Link Local Multicast
Name Resolution protocol `LLMNR
<https://en.wikipedia.org/wiki/Link_Local_Multicast_Name_Resolution>`_.
It currently depends on the iproute command to locate network interfaces on the
host system, and hence only runs only on linux systems which provide iproute.
However, the protocol implementation is not system dependent so, with a modest
amount of additional work, Llamar could also be made to work on other systems.

The LLMNR protocol provides `zero-configuration networking
<https://en.wikipedia.org/wiki/Zero-configuration_networking>`_
as does Apple's "Bonjour" and its linux implementation avahi.  In
other words, it can be used to find the IP addresses of other machines
on the same LAN without a DNS server.  It uses packets which are
slightly modified from DNS packets and supports A, AAAA and PTR
queries. LLMNR is much simpler and much quieter than the relatively
bloated and noisy Bonjour/Avahi.

Modern Windows systems respond to LLMNR queries on any network interface which
has "network discovery" enabled.  This is enabled by default for a "Home
Network" and disabled by default for a "Public Network".

The Llamar package provides a Sender class, which sends LLNMR queries and parses
the responses, and a Responder class which receives and replies to LLMNR queries.
The Responder.run() method, when run as a service, makes the host findable by
Windows computers.  There is also a command line program named busco with will
run a query and report the result.

Applications
-------------

Here is a typical application for Llamar.  You have an embedded linux system,
say running on an Odroid Arm computer.  It provides a webserver on port 80 to be
used by other computers on your network.  The Arm gets addresses dynamically
from DHCP.  You want to be able to connect to its server from a Windows laptop
without having to figure out it current address.  So you create /etc/llamar.conf
specifying the name "odroid" for the wlan0 interface on the Arm.  You start a
service on the Arm which initializes a llamar.Responder and runs its run()
method.  Now you can open a web browser on the Windows laptop and simply type
"odroid" into the go box.

Example
--------

I have a Virtual Box Windows client running on my Ubuntu laptop, which is named
ace.  The client, named VBoxPC, has a bridged network adapter installed with
"network discovery" enabled.

From ace I can find the IP address of VBoxPC like this:

::
   
   culler@ace:~/programs/llamar$ bin/busco VboxPC
   A: 192.168.0.121
   culler@ace:~/programs/llamar$ bin/busco -q AAAA VboxPC
   AAAA: ::c82e:9545:4e69:b52b
   AAAA: fe80::c82e:9545:4e69:b52b
   culler@ace:~/programs/llamar$ bin/busco -q PTR 192.168.0.121
   PTR: VboxPC

   
Now I would like to find the address of ace from VBoxPC.  First I start an LLMNR
Responder running on ace.  We will enable debug mode to see what happens.   
   
::
   
   culler@ace:~/programs/llamar$ python3
   Python 3.5.2 (default, Nov 17 2016, 17:05:23) 
   [GCC 5.4.0 20160609] on linux
   Type "help", "copyright", "credits" or "license" for more information.
   >>> import llmnr
   >>> R = llmnr.Responder()
   >>> R.debug()
   >>> R.run()

Next, I will go over to VboxPC and ping ace.  This will require the PC to find an
address for ace, which it will do by broadcasting LLMNR queries.  The Responder on
ace will reply with an address.  This is what I see on ace, in debug mode:

::
   
   DEBUG:llamar:Received datagram.
   DEBUG:llamar:Received A query from ('fe80::c82e:9545:4e69:b52b%wlan0', 59293, 0, 2) for ace.
   DEBUG:llamar:Responding.
   DEBUG:llamar:Received datagram.
   DEBUG:llamar:Received A query from ('192.168.0.121', 54700) for ace.
   DEBUG:llamar:Responding.
   DEBUG:llamar:Received datagram.
   DEBUG:llamar:Received AAAA query from ('fe80::c82e:9545:4e69:b52b%wlan0', 60647, 0, 2) for ace.
   DEBUG:llamar:Responding.

And, on VBoxPC, when I run the ping command it looks like this:

::
   
   C:\Users\culler>ping ace
   
   Pinging ace [::bcba:928d:7d4f:530a] with 32 bytes of data:
   Reply from ::bcba:928d:7d4f:530a: time<1ms
   Reply from ::bcba:928d:7d4f:530a: time<1ms
   Reply from ::bcba:928d:7d4f:530a: time<1ms
   Reply from ::bcba:928d:7d4f:530a: time<1ms
   
   Ping statistics for ::bcba:928d:7d4f:530a:
      Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),
   Approximate round trip times in milli-seconds:
      Minimum = 0ms, Maximum = 0ms, Average = 0ms

Now let's kill the Responder and close all of its sockets:

::
   
   ^CTraceback (most recent call last):
   File "<stdin>", line 1, in <module>
   File "/home/culler/programs/llamar/llmnr/responder.py", line 244, in run
   [], [])
   KeyboardInterrupt
   >>> R.close()

And, this is what happens if I try the ping again with no responder running
on ace:

::
   
   C:\Users\culler>ping ace
   Ping request could not find host ace. Please check the name and try again.
   
      
Installation
-------------

Run

::
   
   sudo python setup.py install

to install the python module.  To run an LLMNR Responder you need to edit the
template file llamar/etc/llmnr.conf provided in the package and copy the result
into /etc.  The configuration simply assigns a name to each interface which you
want the responder to listen to.  To run the Responder as a system service on
your linux box, you need to install a service script in /etc/init (for upstart
systems) or /etc/systemd (for systemd systems.  Templates are provided in the
llamar/etc directory