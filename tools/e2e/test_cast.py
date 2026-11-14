"""Casting, an opt-in (oganesson/core/cast-opt-in.patch, oganesson/settings/cast-settings.patch).

Off, as in a fresh profile: the app menu has no Cast, no browser process opens
the mDNS port, and the browser sends no mDNS or SSDP packet to the local
network, though a page asks for cast devices, a page makes WebRTC candidates,
and chrome://inspect looks for devices. The switch on Settings > System applies at
the next start, with Relaunch until then. On, the menu has Cast, and the
page's question starts discovery: an mDNS query for Cast devices and a DIAL
M-SEARCH. Turned off again, the next start is silent again.

The test sees the packets as any device on the network would: it joins the
mDNS and SSDP multicast groups on each of this machine's interfaces, and the
kernel loops the browser's own packets back to it. A packet counts when it
comes from this machine and from a port one of the browser's processes had a
UDP socket on, so other programs' packets don't. Copies of the class (--repeat
runs them side by side) take turns, since they would share the mDNS port.
Without a multicast interface the test skips.
"""

import fcntl
import json
import os
import re
import socket
import struct
import subprocess
import threading
import time
import unittest

from harness import BrowserTest, Server, wait_for
from test_firefox_sync import FIND

PREF = 'oganesson.google.cast_enabled'
MDNS = ('224.0.0.251', 5353)
SSDP = ('239.255.255.250', 1900)
# The name the Media Router's mDNS query asks for, in DNS wire format.
CAST_NAME = b'\x0b_googlecast\x04_tcp\x05local\x00'
DIAL = b'urn:dial-multiscreen-org:service:dial:1'
# How long a browser that isn't casting gets to send anything.
QUIET = 10
MDNS_PORT = MDNS[1]
# A WebRTC offer's candidates. With WebRTC's mDNS host names, the first
# connection makes the browser's mDNS responder, which opens the mDNS port.
# True when the candidates are named with .local.
WEBRTC = """(async () => {
  const pc = new RTCPeerConnection();
  pc.createDataChannel('x');
  const gathered = new Promise(done => pc.onicegatheringstatechange =
      () => pc.iceGatheringState === 'complete' && done());
  await pc.setLocalDescription(await pc.createOffer());
  await Promise.race([gathered, new Promise(done => setTimeout(done, 5000))]);
  pc.close();
  return pc.localDescription.sdp.includes('.local');
})()"""
# The default Media Receiver app, so a cast: presentation URL.
AVAILABILITY = """new PresentationRequest('cast:CC1AD845').getAvailability()
    .then(a => 'available: ' + a.value, e => e.name)"""
TOGGLE = f"({FIND})('settings-system-page')?.shadowRoot?.querySelector('#googleCast')"
RESTART = f"{TOGGLE}?.querySelector('cr-button')"
LOCK = '/tmp/oganesson-e2e-cast.lock'


def interfaces():
    """(index, address) of each IPv4 interface that is up and multicasts."""
    found = []
    output = subprocess.run(['ip', '-j', '-4', 'addr', 'show', 'up'], capture_output=True,
                            text=True, check=True).stdout
    for link in json.loads(output):
        flags = link.get('flags', [])
        if 'MULTICAST' in flags and 'LOOPBACK' not in flags:
            for info in link.get('addr_info', []):
                found.append((link['ifindex'], info['local']))
    return found


def descendants(pid):
    """`pid` and the processes under it."""
    children = {}
    for entry in filter(str.isdigit, os.listdir('/proc')):
        try:
            with open(f'/proc/{entry}/stat') as stat:
                # After the command's name, which may hold spaces: state, ppid.
                parent = int(stat.read().rsplit(')', 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(parent, []).append(int(entry))
    found, todo = [], [pid]
    while todo:
        found.append(todo.pop())
        todo += children.get(found[-1], [])
    return found


def udp_ports(pids):
    """The local ports of the UDP sockets `pids` have open."""
    inodes = set()
    for pid in pids:
        try:
            for fd in os.listdir(f'/proc/{pid}/fd'):
                match = re.fullmatch(r'socket:\[(\d+)\]', os.readlink(f'/proc/{pid}/fd/{fd}'))
                if match:
                    inodes.add(match[1])
        except OSError:
            continue
    ports = set()
    for table in ('/proc/net/udp', '/proc/net/udp6'):
        with open(table) as lines:
            for line in list(lines)[1:]:
                fields = line.split()
                if fields[9] in inodes:
                    ports.add(int(fields[1].rsplit(':', 1)[1], 16))
    return ports


class Listener:
    """The browser's mDNS and SSDP packets to the local network."""

    def __init__(self, browser_pid):
        self.browser_pid = browser_pid
        self.links = interfaces()
        if not self.links:
            raise unittest.SkipTest('no multicast network interface')
        self.addresses = {address for _, address in self.links}
        self.packets = []
        # The ports the browser had UDP sockets on, looked at every 50 ms: a
        # DIAL search's socket lives for seconds.
        self.ports = set()
        self.sockets = [self.join(*MDNS), self.join(*SSDP)]
        self.threads = [threading.Thread(target=self.read, daemon=True),
                        threading.Thread(target=self.watch, daemon=True)]
        for thread in self.threads:
            thread.start()

    def join(self, group, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Shared with the browser's own socket and the system's mDNS responder.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(('', port))
        for index, _ in set(self.links):
            # struct ip_mreqn: the group, any address, the interface.
            request = struct.pack('=4s4si', socket.inet_aton(group), bytes(4), index)
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, request)
            except OSError as error:
                if error.errno != 98:  # joined already, through another address
                    raise
        sock.settimeout(0.2)
        return sock

    def read(self):
        while self.sockets:
            for sock in list(self.sockets):
                try:
                    data, (address, port) = sock.recvfrom(9000)
                except (TimeoutError, OSError):
                    continue
                if address in self.addresses:
                    self.packets.append((port, data))

    def watch(self):
        while self.sockets:
            pid = self.browser_pid()
            if pid:
                self.ports |= udp_ports(descendants(pid))
            time.sleep(0.05)

    def clear(self):
        self.packets.clear()
        self.ports.clear()

    def close(self):
        sockets, self.sockets = self.sockets, []
        for thread in self.threads:
            thread.join()
        for sock in sockets:
            sock.close()

    def browser_packets(self):
        # The port may show only after the packet: read them first.
        packets = list(self.packets)
        time.sleep(0.2)
        return [data for port, data in packets if port in self.ports]

    def cast_queries(self):
        # A query (QR bit clear) naming the Cast service.
        return [p for p in self.browser_packets()
                if len(p) > 12 and not p[2] & 0x80 and CAST_NAME in p]

    def dial_searches(self):
        return [p for p in self.browser_packets() if p.startswith(b'M-SEARCH') and DIAL in p]


class CastTest(BrowserTest):
    """One browser through off, on and off again, each after a restart."""

    @classmethod
    def setUpClass(cls):
        cls.lock = open(LOCK, 'w')
        fcntl.flock(cls.lock, fcntl.LOCK_EX)
        cls.listener = Listener(lambda: cls.browser.proc.pid if hasattr(cls, 'browser') else None)
        cls.site = Server({'/': (200, {'Content-Type': 'text/html'}, b'<title>cast</title>')})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.site.stop()
        cls.listener.close()
        cls.lock.close()

    def menu_titles(self):
        """The app menu's items, the menu closed again."""
        self.browser.click_view(self.browser.wait_view('BrowserAppMenuButton'))
        wait_for(self.browser.menus, what='the app menu')
        titles = [i['Title'].replace('&', '') for menu in self.browser.menus()
                  for group in menu for i in group]
        self.browser.key('Escape')
        wait_for(lambda: not self.browser.menus(), what='the menu to close')
        return titles

    def on_page(self, script):
        """What `script` gives on a page of the site."""
        page = self.browser.new_tab(self.site.url('/'))
        try:
            wait_for(lambda: page.eval('document.title') == 'cast', what='the page')
            return page.eval(script)
        finally:
            self.browser.close_target(page)

    def assert_quiet(self):
        self.listener.clear()
        # "Cast, save, and share" while casting is on.
        self.assertIn('Save and share', self.menu_titles())
        self.on_page(AVAILABILITY)
        self.assertIs(self.on_page(WEBRTC), False, '.local WebRTC candidates')
        inspect = self.browser.new_tab('chrome://inspect/#devices')
        time.sleep(QUIET)
        self.browser.close_target(inspect)
        self.assertNotEqual(self.listener.ports, set(), "no look at the browser's sockets")
        self.assertNotIn(MDNS_PORT, self.listener.ports, 'an mDNS socket in the browser')
        self.assertEqual(self.listener.browser_packets(), [], 'mDNS or SSDP from the browser')

    def switch(self, on):
        """Turns the switch on or off in Settings and relaunches with it."""
        settings = self.browser.new_tab('chrome://settings/system')
        wait_for(lambda: settings.eval(f'!!{TOGGLE}'), what='the switch')
        self.assertEqual(settings.eval(f'{TOGGLE}.label'), 'Cast to devices on your network')
        self.assertIs(settings.eval(f'{TOGGLE}.checked'), not on)
        self.assertIs(settings.eval(f'!!{RESTART}'), False, 'Relaunch before a change')
        settings.eval(f'{TOGGLE}.click()')
        get = f'chrome.settingsPrivate.getPref({json.dumps(PREF)}).then(p => p.value)'
        wait_for(lambda: settings.eval(get) is on, what='the pref')
        wait_for(lambda: settings.eval(f'!!{RESTART}'), what='Relaunch')
        settings.eval(f'{RESTART}.click()')
        self.browser.follow_relaunch()

    def test_off_on_off(self):
        self.assert_quiet()

        self.switch(on=True)
        self.listener.clear()
        self.assertIn('Cast, save, and share', self.menu_titles())
        # Whether a device answered or not.
        self.assertTrue(self.on_page(AVAILABILITY).startswith('available: '))
        wait_for(self.listener.cast_queries, timeout=30, what='an mDNS query for Cast devices')
        wait_for(self.listener.dial_searches, timeout=30, what='a DIAL search')

        self.switch(on=False)
        self.assert_quiet()


if __name__ == '__main__':
    unittest.main()
