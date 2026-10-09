#!/usr/bin/env python3
"""Checks liboganesson_sync.so end to end against tools/fake_firefox_sync.py.

Signs in, then syncs a small local login list both ways: uploads, Firefox
side adds, edits and deletes, local edits and deletes, and a restart from the
saved state. A server's Retry-After keeps later syncs from contacting it. The local list stands in for the browser's password store and
applies the returned ops the way FirefoxSyncService does.

    python3 tools/check_firefox_sync.py [path/to/liboganesson_sync.so]

Needs NSS (libnss3) and the `cryptography` package.
"""

import ctypes
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fake_firefox_sync  # noqa: E402
from fake_firefox_sync import decrypt, encrypt  # noqa: E402

LIB = Path(__file__).resolve().parent.parent / \
    'work/helium-linux/build/src/out/Default/liboganesson_sync.so'

SET = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p)
HTTP = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p, SET)


# URLs the library requested, and replies that stand in for the server's:
# {URL part: response}.
REQUESTS = []
REPLIES = {}


def http(_ctx, request, out, set_response):
    r = json.loads(request)
    REQUESTS.append(r['url'])
    reply = next((v for k, v in REPLIES.items() if k in r['url']), None)
    if reply:
        set_response(out, json.dumps(reply).encode())
        return
    body = r['body'].encode() if r['body'] is not None else None
    req = urllib.request.Request(r['url'], data=body, method=r['method'], headers=r['headers'])
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            res = {'status': resp.status, 'headers': dict(resp.headers), 'body': resp.read().decode()}
    except urllib.error.HTTPError as e:
        res = {'status': e.code, 'headers': dict(e.headers), 'body': e.read().decode()}
    except OSError as e:
        res = {'error': str(e)}
    set_response(out, json.dumps(res).encode())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def login(host, user, password, changed, **extra):
    return dict({'hostname': host, 'formSubmitURL': host, 'httpRealm': None,
                 'username': user, 'password': password, 'usernameField': 'u',
                 'passwordField': 'p', 'timeCreated': 1000, 'timePasswordChanged': changed,
                 'timeLastUsed': 0, 'timesUsed': 0}, **extra)


def key(record):
    return (record['hostname'], record.get('httpRealm'), record['username'])


MAC = '@testpilot-containers'




def check_backoff(raw_call, profiles, saved):
    """A token or storage server's 503 with Retry-After: syncs until then
    contact nothing and fail with the deadline, which a sync returns."""
    for n, part in enumerate(('/token/1.0/sync/1.5', '/info/collections')):
        profile = os.path.join(profiles, f'backoff{n}')
        os.mkdir(profile)
        REPLIES[part] = {'status': 503, 'headers': {'retry-after': '3600'}, 'body': '{}'}
        engines = {'passwords': {'state': '', 'local': []}}
        first = raw_call('sync', profile=profile, engines=engines, **saved)
        assert 'error' in first and first['retry_after'] > (time.time() + 3500) * 1000, first
        REQUESTS.clear()
        second = raw_call('sync', profile=profile, engines=engines, **saved)
        assert REQUESTS == [], REQUESTS
        assert second['retry_after'] == first['retry_after'], second
        REPLIES.clear()
    print('ok: Retry-After stops syncs until its deadline')


def main():
    lib_path = sys.argv[1] if len(sys.argv) > 1 else LIB
    server, base, state = fake_firefox_sync.serve()
    os.environ['OGANESSON_FXA_SERVER'] = base
    lib = ctypes.CDLL(str(lib_path))
    lib.og_call.restype = ctypes.c_void_p
    callback = HTTP(http)
    lib.og_init(callback)

    def raw_call(method, **args):
        raw = lib.og_call(None, method.encode(), json.dumps(args).encode())
        result = json.loads(ctypes.string_at(raw))
        lib.og_free(ctypes.c_void_p(raw))
        return result

    def call(method, **args):
        result = raw_call(method, **args)
        if 'error' in result:
            raise AssertionError(f'{method}: {result["error"]}')
        return result['ok']

    def firefox(method='GET', path='', record=None):
        data = json.dumps(record).encode() if record else None
        req = urllib.request.Request(base + '/_firefox/logins' + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def firefox_live():
        return {r['hostname']: r for r in firefox() if not r.get('deleted')}

    print(call('version'))

    # Sign in: the fake's sign-in page redirects straight back.
    # Profiles are folders: the library keeps its stores there.
    profiles = tempfile.mkdtemp()
    p, restarted = os.path.join(profiles, 'p'), os.path.join(profiles, 'restarted')
    os.mkdir(p)
    os.mkdir(restarted)
    begin = call('begin_signin', profile=p)
    try:
        urllib.request.build_opener(NoRedirect).open(begin['url'])
        raise AssertionError('no redirect')
    except urllib.error.HTTPError as e:
        location = e.headers['Location']
    assert location.startswith(begin['redirect']), location
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(location).query))
    signed_in = call('complete_signin', profile=p, code=query['code'], state=query['state'])
    assert signed_in['email'] == 'fake@example.com'
    saved = {'account': signed_in['account']}
    local = [login('https://a.example', 'ann', 'pa', 1000)]

    def sync(profile=p):
        nonlocal saved
        engines = {'passwords': {'state': saved.pop('passwords', ''), 'local': local}}
        result = call('sync', profile=profile, engines=engines, **saved)
        passwords = result['engines']['passwords']
        assert 'error' not in passwords, passwords
        saved = {k: result[k] for k in ('account', 'global')}
        saved['passwords'] = passwords['state']
        for op in passwords['ops']:
            if op['op'] == 'delete':
                local[:] = [r for r in local if key(r) != key(op['key'])]
                continue
            new, old = op['login'], key(op['replaces'] or op['login'])
            local[:] = [r for r in local if key(r) != old] + [new]
        return passwords['ops']

    # First sync uploads the local login.
    assert sync() == []
    assert firefox_live()['https://a.example']['password'] == 'pa'
    print('ok: first sync uploads local logins')

    # Firefox adds one and changes a's password: both come down.
    firefox('POST', record=login('https://b.example', 'bob', 'pb', 2000, id='bbbbbbbbbbbb'))
    a = firefox_live()['https://a.example']
    firefox('POST', record=dict(a, password='pa2', timePasswordChanged=3000))
    ops = sync()
    assert len(ops) == 2, ops
    by_host = {r['hostname']: r for r in local}
    assert by_host['https://b.example']['password'] == 'pb'
    assert by_host['https://a.example']['password'] == 'pa2'
    assert sync() == []
    print('ok: Firefox additions and edits download')

    # Local edit and local deletion go up.
    for r in local:
        if r['hostname'] == 'https://b.example':
            r.update(password='pb2', timePasswordChanged=4000)
    local[:] = [r for r in local if r['hostname'] != 'https://a.example']
    assert sync() == []
    live = firefox_live()
    assert live['https://b.example']['password'] == 'pb2'
    assert 'https://a.example' not in live
    assert any(r.get('deleted') and r['id'] == a['id'] for r in firefox())
    print('ok: local edits and deletions upload')

    # Firefox deletes b: removed locally.
    firefox('DELETE', '/bbbbbbbbbbbb')
    ops = sync()
    assert ops == [{'op': 'delete', 'key': {'hostname': 'https://b.example',
                                            'httpRealm': None, 'username': 'bob'}}], ops
    assert local == []
    print('ok: Firefox deletions remove local logins')

    # A restart restores the account and state from what the browser saved.
    local.append(login('https://c.example', 'cat', 'pc', 5000))
    assert sync(profile=restarted) == []
    assert firefox_live()['https://c.example']['password'] == 'pc'
    print('ok: saved state restores')

    # Firefox renames the user: the local login under the old key is replaced.
    c = firefox_live()['https://c.example']
    firefox('POST', record=dict(c, username='cathy', timePasswordChanged=6000))
    ops = sync(profile=restarted)
    assert [(op['login']['username'], op['replaces']['username']) for op in ops] == \
        [('cathy', 'cat')], ops
    assert [r['username'] for r in local] == ['cathy']
    print('ok: Firefox renames replace the local login')

    check_backoff(raw_call, profiles, {'account': saved['account']})

    call('signout', profile=restarted, account=saved['account'])
    server.shutdown()
    print('all Firefox Sync checks passed')


if __name__ == '__main__':
    main()
