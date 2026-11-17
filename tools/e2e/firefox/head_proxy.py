"""For the ports of Firefox's proxy tests: Gecko's proxy service in the form
this browser has, and a proxy server.

Firefox's tests ask Gecko's proxy service which proxies it chose for a URL
(getProxyInfo(), nsIProtocolProxyService.asyncResolve()). Here ProxyTest's
proxy_info() reads it from the browser's NetLog (--log-net-log): the browser
requests the URL, and the log's PROXY_RESOLUTION_SERVICE_RESOLVED_PROXY_LIST
event for it has the proxy list, before the browser puts the proxies that
failed lately last, as Gecko's answer is before any failover. Each host
that the test doesn't serve resolves to nothing, so the proxies that Firefox's
tests name, such as 1.2.3.4 or foo.bar, never reach the network.

ProxyServer stands for the proxies of Firefox's tests (createHttpServer()
answering as a proxy, SocksTestServer): a local HTTP and SOCKS proxy that
records what reaches it."""

import json
import shutil
import socket
import socketserver
import struct
import tempfile
import threading
import time
from pathlib import Path

from extension_test_utils import FirefoxTest

# nsIProxyInfo.TRANSPARENT_PROXY_RESOLVES_HOST: the proxy resolves the host.
TRANSPARENT_PROXY_RESOLVES_HOST = 1
# How long Chromium keeps a proxy that failed out of use, in seconds
# (ProxyList::Fallback()), where Firefox has the proxy's failoverTimeout.
RETRY_DELAY = 300
# Chromium's proxy schemes in a proxy list, as Firefox's types.
TYPES = {'PROXY': 'http', 'HTTPS': 'https', 'SOCKS': 'socks4', 'SOCKS5': 'socks'}


def loose_equal(actual, expected):
    """JavaScript's ==, for the values Firefox's tests compare: null and
    undefined (None) equal only each other, and a number equals its
    string."""
    if actual is None or expected is None:
        return actual is None and expected is None
    if isinstance(actual, str) != isinstance(expected, str):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return False
    return actual == expected


def firefox_proxy_info(proxy_list):
    """A Chromium proxy list ("PROXY 1.2.3.4:8080;SOCKS5 foo.bar:1080;DIRECT")
    as Gecko's nsIProxyInfo, a dict whose failoverProxy is the next one; None
    for a direct connection, as Gecko gives. Chromium's proxies carry no
    credentials. Its SOCKS 5 proxy always resolves the host, its SOCKS 4 one
    never does."""
    chain = None
    for entry in reversed([e.strip() for e in proxy_list.split(';') if e.strip()]):
        scheme, _, server = entry.partition(' ')
        if scheme == 'DIRECT':
            proxy = {'type': 'direct', 'host': None, 'port': -1}
        else:
            host, _, port = server.rpartition(':')
            proxy = {'type': TYPES.get(scheme, scheme), 'host': host.strip('[]'), 'port': int(port)}
        proxy.update(username='', password='',
                     flags=TRANSPARENT_PROXY_RESOLVES_HOST if proxy['type'] == 'socks' else 0,
                     failoverTimeout=RETRY_DELAY, failoverProxy=chain)
        chain = proxy
    if chain and chain['type'] == 'direct':
        return None
    return chain


def check_proxy_chain(test, proxy_info, expected_proxy_info, default_port=None):
    """The loop of Firefox's proxy tests over the proxies of a chain (Gecko's
    nsIProxyInfo and its failoverProxy), each against the expected one; a
    missing port is `default_port`. The expected proxies left over."""
    proxy_used = proxy_info
    while proxy_used:
        expected = expected_proxy_info or {}
        host, port, kind = expected.get('host'), expected.get('port'), expected.get('type')
        username, password = expected.get('username'), expected.get('password')
        proxy_dns, failover_timeout = expected.get('proxyDNS'), expected.get('failoverTimeout')
        test.equal(proxy_used['host'], host, f'Expected proxy host to be {host}')
        test.equal(proxy_used['port'], port or default_port, f'Expected proxy port to be {port}')
        test.equal(proxy_used['type'], kind, f'Expected proxy type to be {kind}')
        # May be null or undefined depending on use of newProxyInfoWithAuth or newProxyInfo
        test.equal(proxy_used['username'] or '', username or '',
                   f'Expected proxy username to be {username}')
        test.equal(proxy_used['password'] or '', password or '',
                   f'Expected proxy password to be {password}')
        test.equal(proxy_used['flags'], 0 if proxy_dns is None else proxy_dns,
                   f'Expected proxyDNS to be {proxy_dns}')
        # Default timeout is 10
        test.equal(proxy_used['failoverTimeout'], failover_timeout or 10,
                   f'Expected failoverTimeout to be {failover_timeout}')
        expected_proxy_info = expected.get('failoverProxy')
        proxy_used = proxy_used['failoverProxy']
    return expected_proxy_info


class NetLog:
    """The browser's NetLog file, read as the browser writes it: a line of
    constants, then an event a line. The browser writes its events in
    batches of 15."""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.types = None
        # The URL of each request (the events' source), once it has one.
        self.urls = {}

    def read(self):
        """The events written since the last read, each with its type's name
        (`name`) and its request's URL (`url`)."""
        try:
            with open(self.path, 'rb') as log:
                log.seek(self.offset)
                text = log.read()
        except FileNotFoundError:
            return []
        # Up to the last whole line: the browser may be writing one.
        end = text.rfind(b'\n') + 1
        self.offset += end
        events = []
        for line in text[:end].decode(errors='replace').splitlines():
            line = line.strip().rstrip(',')
            if line.startswith('{"constants":'):
                constants = json.loads(line[len('{"constants":'):])
                self.types = {number: name for name, number
                              in constants['logEventTypes'].items()}
                continue
            if not line.startswith('{"') or self.types is None:
                continue
            event = json.loads(line)
            source = event['source']['id']
            if 'url' in event.get('params', {}):
                self.urls[source] = event['params']['url']
            event['name'] = self.types.get(event['type'])
            event['url'] = self.urls.get(source)
            events.append(event)
        return events


class ProxyTest(FirefoxTest):
    """A Firefox proxy test: the browser writes its NetLog, and only the
    test's own hosts resolve."""

    host_rules = ('MAP * ~NOTFOUND', 'EXCLUDE localhost', 'EXCLUDE 127.0.0.1')
    # The browser's own requests reach the add-ons' listeners too, which
    # Firefox's xpcshell tests don't have: the tests start once the bundled
    # uBlock Origin has its lists, which it holds requests for until then,
    # it doesn't update them (setUpClass()), and the browser downloads no
    # spellcheck dictionary.
    wait_ubo = True
    prefs = {'browser': {'enable_spellchecking': False}}

    @classmethod
    def setUpClass(cls):
        cls.net_log_folder = Path(tempfile.mkdtemp(prefix='oganesson-netlog-'))
        cls.net_log = NetLog(cls.net_log_folder / 'net.json')
        cls.browser_args = (*cls.browser_args, f'--log-net-log={cls.net_log.path}')
        # A closed port, which a request to fails at once.
        with socket.socket() as closed:
            closed.bind(('127.0.0.1', 0))
            cls.closed_port = closed.getsockname()[1]
        super().setUpClass()
        ubo = cls.browser.ubo_background()
        try:
            ubo.eval('µBlock.changeUserSettings("autoUpdate", false), 0', gesture=False)
        finally:
            ubo.close()

    @classmethod
    def tearDownClass(cls):
        # Kept with the browser's profile and log, if they are.
        if cls.net_log.path.exists():
            shutil.move(cls.net_log.path, cls.browser.root / 'net.json')
        super().tearDownClass()
        shutil.rmtree(cls.net_log_folder, ignore_errors=True)

    def equal(self, actual, expected, message):
        """xpcshell's equal(): JavaScript's ==, which fails the test when it
        ends, as is_() does."""
        self.check(loose_equal(actual, expected),
                   f'{message} - Expected: {expected}, Actual: {actual}')

    def ok(self, value, message):
        """xpcshell's ok()."""
        self.check(bool(value), message)

    @staticmethod
    def fetch_in_page(page, url):
        """Starts a request for `url` from `page`, and doesn't wait for it."""
        page.eval(f'fetch({json.dumps(url)}, {{mode: "no-cors", cache: "no-store"}})'
                  '.catch(() => {}), 0', gesture=False)

    def await_resolution(self, url, page, known, timeout=5):
        """The proxy list ("PROXY 1.2.3.4:8080;DIRECT") the browser resolves
        for a request to `url` that isn't one of the `known` ones (the NetLog's
        sources), within `timeout` seconds, or None. `page` requests a closed
        local port meanwhile, so that the browser writes its batches of
        events."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.net_log.read():
                if (event['name'] == 'PROXY_RESOLUTION_SERVICE_RESOLVED_PROXY_LIST'
                        and event['url'] == url and event['source']['id'] not in known):
                    return event['params']['proxy_info']
            self.fetch_in_page(page, f'http://127.0.0.1:{self.closed_port}/')
            time.sleep(0.2)
        return None

    def proxy_info(self, url='http://www.mozilla.org/'):
        """Firefox's getProxyInfo(): the proxies the browser chose for `url`,
        as Gecko's nsIProxyInfo (firefox_proxy_info()), or None for a direct
        connection. The request comes from a blank tab of its own. This
        browser requests only http: and https: URLs (it has no FTP), so it
        resolves no proxy for another: None. A request whose resolution
        doesn't show fails the test."""
        if not url.startswith(('http:', 'https:')):
            return None
        page = self.open_tab('about:blank')
        try:
            self.net_log.read()
            known = set(self.net_log.urls)
            self.fetch_in_page(page, url)
            proxy_list = self.await_resolution(url, page, known)
        finally:
            self.browser.close_target(page)
        if proxy_list is None:
            raise AssertionError(f"no proxy resolution for {url} in the browser's NetLog")
        return firefox_proxy_info(proxy_list)


class ProxyServer:
    """A local proxy that records each request that reaches it, in
    `requests`: ('http', url) for an HTTP request for a URL, which it answers
    with `answer` (status, headers, body); ('connect', host:port) for a
    CONNECT, which it refuses with `connect_status`; and ('socks4' or
    'socks', host:port, username) for a SOCKS 4 or 5 connection, after which
    it answers the HTTP request in it with "OK", as Firefox's SocksTestServer
    does. With `username` and `password`, a SOCKS 5 client must give them;
    `credentials` lists those given."""

    def __init__(self, answer=(200, {'Content-Type': 'text/plain'}, b''), connect_status=404,
                 username=None, password=None):
        self.answer = answer
        self.connect_status = connect_status
        self.username = username
        self.password = password
        self.requests = []
        self.credentials = []
        proxy = self

        class Handler(socketserver.BaseRequestHandler):

            def handle(self):
                first = self.request.recv(1, socket.MSG_PEEK)
                try:
                    if first == b'\x04':
                        proxy.socks4(self.request)
                    elif first == b'\x05':
                        proxy.socks5(self.request)
                    elif first:
                        proxy.http(self.request)
                except OSError:
                    pass  # The client went.

        self.server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    @staticmethod
    def read(connection, size):
        data = b''
        while len(data) < size:
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise ConnectionError('closed')
            data += chunk
        return data

    @staticmethod
    def read_until(connection, end):
        data = b''
        while not data.endswith(end):
            chunk = connection.recv(1)
            if not chunk:
                raise ConnectionError('closed')
            data += chunk
        return data

    def http(self, connection):
        head = self.read_until(connection, b'\r\n\r\n').decode(errors='replace')
        method, target, _ = head.split('\r\n', 1)[0].split(' ', 2)
        if method == 'CONNECT':
            self.requests.append(('connect', target))
            connection.sendall(f'HTTP/1.1 {self.connect_status} Proxy not found\r\n'
                               'Content-Length: 0\r\n\r\n'.encode())
            return
        self.requests.append(('http', target))
        status, headers, body = self.answer
        reply = f'HTTP/1.1 {status} OK\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in headers.items())
        connection.sendall(f'{reply}Content-Length: {len(body)}\r\n\r\n'.encode() + body)

    def tunnel(self, connection):
        """The HTTP request through the SOCKS tunnel, answered "OK", with no
        favicon, so that a tab requests nothing more."""
        self.read_until(connection, b'\r\n\r\n')
        body = b'<link rel="icon" href="data:,">OK'
        connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: %d\r\n'
                           b'Content-Type: text/html\r\n\r\n%s' % (len(body), body))

    def socks4(self, connection):
        _, _, port, address = struct.unpack('>BBH4s', self.read(connection, 8))
        username = self.read_until(connection, b'\0')[:-1].decode()
        host = socket.inet_ntoa(address)
        if address.startswith(b'\0\0\0') and address != b'\0\0\0\0':
            host = self.read_until(connection, b'\0')[:-1].decode()  # SOCKS 4a
        self.requests.append(('socks4', f'{host}:{port}', username))
        connection.sendall(b'\0\x5a' + b'\0' * 6)
        self.tunnel(connection)

    def socks5(self, connection):
        _, count = self.read(connection, 2)
        self.read(connection, count)
        username = None
        if self.username or self.password:
            # Username and password, whatever the client offers, as
            # Firefox's server asks.
            connection.sendall(b'\x05\x02')
            _, length = self.read(connection, 2)
            username = self.read(connection, length).decode()
            password = self.read(connection, self.read(connection, 1)[0]).decode()
            self.credentials.append((username, password))
            if (username, password) != (self.username, self.password):
                connection.sendall(b'\x01\x01')
                return
            connection.sendall(b'\x01\x00')
        else:
            connection.sendall(b'\x05\x00')
        _, _, _, kind = self.read(connection, 4)
        if kind == 1:
            host = socket.inet_ntoa(self.read(connection, 4))
        elif kind == 4:
            host = socket.inet_ntop(socket.AF_INET6, self.read(connection, 16))
        else:
            host = self.read(connection, self.read(connection, 1)[0]).decode()
        port = struct.unpack('>H', self.read(connection, 2))[0]
        self.requests.append(('socks', f'{host}:{port}', username))
        connection.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x50')
        self.tunnel(connection)
