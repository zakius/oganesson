#!/usr/bin/env python3
"""A local stand-in for Mozilla's account, token and Sync storage servers.

Tests oganesson's Firefox Sync without a Mozilla account:

    python3 tools/fake_firefox_sync.py --port 8555 &
    OGANESSON_FXA_SERVER=http://127.0.0.1:8555 ./oganesson.py run

Sign-in finishes at once: the fake /authorization redirects straight back
with a code. /_firefox/logins plays Firefox: GET lists the passwords
collection decrypted, POST adds or replaces a login (JSON with an "id"), and
DELETE /_firefox/logins/<id> uploads a tombstone.

Nothing is authenticated or persisted. Needs the `cryptography` package.
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.concatkdf import ConcatKDFHash

SYNC_SCOPE = 'https://identity.mozilla.com/apps/oldsync'


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def unb64url(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def jwe_for(keys_jwk, plaintext):
    """ECDH-ES + A256GCM compact JWE to the client's P-256 key, as FxA sends
    scoped keys."""
    peer = ec.EllipticCurvePublicNumbers(
        int.from_bytes(unb64url(keys_jwk['x']), 'big'),
        int.from_bytes(unb64url(keys_jwk['y']), 'big'),
        ec.SECP256R1()).public_key()
    eph = ec.generate_private_key(ec.SECP256R1())
    nums = eph.public_key().public_numbers()
    header = {'alg': 'ECDH-ES', 'enc': 'A256GCM', 'epk': {
        'kty': 'EC', 'crv': 'P-256',
        'x': b64url(nums.x.to_bytes(32, 'big')),
        'y': b64url(nums.y.to_bytes(32, 'big'))}}
    protected = b64url(json.dumps(header).encode())
    z = eph.exchange(ec.ECDH(), peer)
    alg = b'A256GCM'
    other = (len(alg).to_bytes(4, 'big') + alg + (0).to_bytes(4, 'big') +
             (0).to_bytes(4, 'big') + (256).to_bytes(4, 'big'))
    key = ConcatKDFHash(hashes.SHA256(), 32, other).derive(z)
    iv = os.urandom(12)
    sealed = AESGCM(key).encrypt(iv, plaintext.encode(), protected.encode())
    return '.'.join([protected, '', b64url(iv), b64url(sealed[:-16]),
                     b64url(sealed[-16:])])


def encrypt(bundle, cleartext):
    """A Sync 1.5 encrypted payload: AES-256-CBC, HMAC over the base64."""
    enc_key, hmac_key = bundle
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    data = padder.update(cleartext.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).encryptor()
    ct = base64.b64encode(enc.update(data) + enc.finalize())
    return json.dumps({'ciphertext': ct.decode(),
                       'IV': base64.b64encode(iv).decode(),
                       'hmac': hmac.new(hmac_key, ct, hashlib.sha256).hexdigest()})


def decrypt(bundle, payload):
    enc_key, hmac_key = bundle
    p = json.loads(payload)
    expected = hmac.new(hmac_key, p['ciphertext'].encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, p['hmac']):
        raise ValueError('bad hmac')
    dec = Cipher(algorithms.AES(enc_key),
                 modes.CBC(base64.b64decode(p['IV']))).decryptor()
    data = dec.update(base64.b64decode(p['ciphertext'])) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(data) + unpadder.finalize()).decode()


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.ksync = os.urandom(64)
        self.kid = '1700000000000-' + b64url(hashlib.sha256(self.ksync).digest()[:16])
        self.pending = {}      # oauth code -> keys_jwk
        self.collections = {}  # name -> {id: bso}
        self.modified = {}     # name -> timestamp
        self.last = 0.0
        self.log = []
        # hold(): requests under a path prefix wait until let_go().
        self.held_prefix = None
        self.held = threading.Event()
        self.released = threading.Event()

    def hold(self, prefix):
        self.held.clear()
        self.released.clear()
        self.held_prefix = prefix

    def let_go(self):
        self.held_prefix = None
        self.released.set()

    def now(self):
        t = round(max(time.time(), self.last + 0.01), 2)
        self.last = t
        return t

    def root_bundle(self):
        return self.ksync[:32], self.ksync[32:]

    def bundle(self, coll):
        keys = self.collections.get('crypto', {}).get('keys')
        if not keys:
            raise ValueError('no crypto/keys yet: sync the browser once first')
        clear = json.loads(decrypt(self.root_bundle(), keys['payload']))
        pair = clear.get('collections', {}).get(coll, clear['default'])
        return base64.b64decode(pair[0]), base64.b64decode(pair[1])

    def passwords_bundle(self):
        return self.bundle('passwords')

    def add_engine(self, name, version=1):
        """Adds an engine to meta/global, as a Firefox that syncs it does."""
        meta = self.collections['meta']['global']
        payload = json.loads(meta['payload'])
        payload['engines'][name] = {'version': version, 'syncID': b64url(os.urandom(9))}
        self.put('meta', dict(meta, payload=json.dumps(payload)), self.now())

    def put(self, coll, bso, ts):
        bso = dict(bso, modified=ts)
        self.collections.setdefault(coll, {})[bso['id']] = bso
        self.modified[coll] = ts


class Handler(BaseHTTPRequestHandler):
    state: State
    base: str

    def log_message(self, fmt, *args):
        self.state.log.append(f'{self.command} {self.path.split("?")[0]}')

    def reply(self, status, body=None, headers=()):
        data = b'' if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        now = self.state.now()
        self.send_header('X-Weave-Timestamp', f'{now:.2f}')
        self.send_header('X-Timestamp', str(int(now)))  # the token server's
        headers = list(headers)
        if not any(name == 'X-Last-Modified' for name, _ in headers):
            headers.append(('X-Last-Modified', f'{now:.2f}'))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b''
        return json.loads(raw) if raw else {}

    def do_GET(self):
        self.route('GET')

    def do_POST(self):
        self.route('POST')

    def do_PUT(self):
        self.route('PUT')

    def do_DELETE(self):
        self.route('DELETE')

    def route(self, method):
        url = urllib.parse.urlsplit(self.path)
        path, query = url.path, dict(urllib.parse.parse_qsl(url.query))
        prefix = self.state.held_prefix
        if prefix and path.startswith(prefix):
            self.state.held.set()
            self.state.released.wait(120)
        with self.state.lock:
            if path.startswith('/storage/1.5/1/'):
                return self.storage(method, path[len('/storage/1.5/1/'):], query)
            if path.startswith('/_firefox/logins'):
                return self.firefox(method, path[len('/_firefox/logins'):])
            return self.accounts(method, path, query)

    def accounts(self, method, path, query):
        b = self.base
        if path == '/.well-known/fxa-client-configuration':
            return self.reply(200, {
                'auth_server_base_url': b + '/auth', 'oauth_server_base_url': b + '/oauth',
                'profile_server_base_url': b + '/profile',
                'sync_tokenserver_base_url': b + '/token',
                'pairing_server_base_url': b + '/pair'})
        if path == '/.well-known/openid-configuration':
            return self.reply(200, {
                'authorization_endpoint': b + '/authorization',
                'introspection_endpoint': b + '/oauth/v1/introspect', 'issuer': b,
                'jwks_uri': b + '/oauth/v1/jwks', 'token_endpoint': b + '/oauth/v1/token',
                'userinfo_endpoint': b + '/profile/v1/profile'})
        if path == '/authorization':
            code = b64url(os.urandom(16))
            self.state.pending[code] = json.loads(unb64url(query['keys_jwk']))
            target = query['redirect_uri'] + '?' + urllib.parse.urlencode(
                {'code': code, 'state': query['state']})
            self.send_response(302)
            self.send_header('Location', target)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        if path.endswith('/v1/oauth/token') or path.endswith('/v1/token'):
            req = self.body()
            resp = {'access_token': 'access-' + b64url(os.urandom(8)),
                    'token_type': 'bearer', 'expires_in': 3600,
                    'scope': req.get('scope') or f'{SYNC_SCOPE} profile'}
            if req.get('grant_type') == 'authorization_code':
                keys_jwk = self.state.pending.pop(req.get('code'), None)
                if keys_jwk is None:
                    return self.reply(400, {'errno': 108, 'message': 'unknown code'})
                resp['refresh_token'] = 'refresh-' + b64url(os.urandom(8))
                resp['keys_jwe'] = jwe_for(keys_jwk, json.dumps({SYNC_SCOPE: {
                    'kty': 'oct', 'scope': SYNC_SCOPE, 'k': b64url(self.state.ksync),
                    'kid': self.state.kid}}))
            return self.reply(200, resp)
        if path == '/profile/v1/profile':
            return self.reply(200, {'uid': 'fakeuid', 'email': 'fake@example.com',
                                    'displayName': 'Fake User',
                                    'avatar': b + '/profile/avatar.png',
                                    'avatarDefault': False})
        if path == '/profile/avatar.png':
            # A 1x1 red PNG.
            data = base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==')
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None
        if path.startswith('/auth/v1/account/device'):
            device = {'id': 'fakedevice', 'name': 'oganesson', 'type': 'desktop',
                      'isCurrentDevice': True, 'pushEndpointExpired': False,
                      'availableCommands': {}, 'location': {}, 'lastAccessTime': 0}
            return self.reply(200, [device] if path.endswith('devices') else device)
        if path == '/token/1.0/sync/1.5':
            return self.reply(200, {
                'id': 'hawk-id', 'key': b64url(os.urandom(32)), 'uid': 1,
                'api_endpoint': b + '/storage/1.5/1', 'duration': 3600,
                'hashed_fxa_uid': 'fakehash'})
        # Destroy tokens, attached clients and the like: accept.
        return self.reply(200, {})

    def storage(self, method, rest, query):
        st = self.state
        parts = rest.split('/')
        if rest == 'info/collections':
            return self.reply(200, st.modified, [
                ('X-Last-Modified', f'{max(st.modified.values(), default=0):.2f}')])
        if rest == 'info/configuration':
            return self.reply(200, {})
        if parts[0] != 'storage':
            return self.reply(404, {})
        if len(parts) == 1 and method == 'DELETE':
            st.collections.clear()
            st.modified.clear()
            return self.reply(200, {'modified': st.now()})
        coll = parts[1]
        items = st.collections.get(coll, {})
        coll_ts = [('X-Last-Modified', f'{st.modified.get(coll, 0):.2f}')]
        if len(parts) == 3:
            bso_id = parts[2]
            if method == 'GET':
                bso = items.get(bso_id)
                return self.reply(200, bso, coll_ts) if bso else self.reply(404, {})
            if method == 'PUT':
                ts = st.now()
                st.put(coll, dict(self.body(), id=bso_id), ts)
                return self.reply(200, ts, [('X-Last-Modified', f'{ts:.2f}')])
            if method == 'DELETE':
                items.pop(bso_id, None)
                return self.reply(200, {'modified': st.now()})
        if method == 'GET':
            newer = float(query.get('newer', 0))
            found = sorted((b for b in items.values() if b['modified'] > newer),
                           key=lambda b: b['modified'])
            if 'full' not in query:
                found = [b['id'] for b in found]
            return self.reply(200, found, coll_ts + [('X-Weave-Records', str(len(found)))])
        if method == 'POST':
            ts = st.now()
            ids = []
            for bso in self.body():
                st.put(coll, bso, ts)
                ids.append(bso['id'])
            result = {'modified': ts, 'success': ids, 'failed': {}}
            if query.get('batch') and not query.get('commit'):
                result['batch'] = 'fakebatch'
                return self.reply(202, result, [('X-Last-Modified', f'{ts:.2f}')])
            return self.reply(200, result, [('X-Last-Modified', f'{ts:.2f}')])
        if method == 'DELETE':
            st.collections.pop(coll, None)
            st.modified.pop(coll, None)
            return self.reply(200, {'modified': st.now()})
        return self.reply(404, {})

    def firefox(self, method, rest):
        st = self.state
        try:
            bundle = st.passwords_bundle()
        except ValueError as e:
            return self.reply(409, {'error': str(e)})
        if method == 'GET':
            # Tombstones from application-services carry the id only in the BSO.
            return self.reply(200, [dict(json.loads(decrypt(bundle, b['payload'])), id=b['id'])
                                    for b in st.collections.get('passwords', {}).values()])
        if method == 'POST':
            login = self.body()
            st.put('passwords', {'id': login['id'],
                                 'payload': encrypt(bundle, json.dumps(login))}, st.now())
            return self.reply(200, login)
        if method == 'DELETE':
            bso_id = rest.strip('/')
            tombstone = json.dumps({'id': bso_id, 'deleted': True})
            st.put('passwords', {'id': bso_id, 'payload': encrypt(bundle, tombstone)},
                   st.now())
            return self.reply(200, {})
        return self.reply(404, {})


def serve(port=0):
    """Starts the fake in a thread; returns (server, base URL, State)."""
    state = State()
    # A class per server, so that several fakes can run at once.
    handler = type('Handler', (Handler,), {})
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    base = f'http://127.0.0.1:{server.server_address[1]}'
    handler.state, handler.base = state, base
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, base, state


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=8555)
    args = parser.parse_args()
    server, base, state = serve(args.port)
    print(f'Fake Firefox Sync at {base}; set OGANESSON_FXA_SERVER={base}', file=sys.stderr)
    try:
        while True:
            time.sleep(1)
            while state.log:
                print(state.log.pop(0), file=sys.stderr)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == '__main__':
    main()
