"""The browser test runs' CPUs and memory: those the system gives the build
containers.

The machine's docker-cpus-by-screen service sets the CPUs of the user
manager's user.slice, where rootless podman runs tennessine's builds, by
screen lock state (all but core 0 while locked, die 1 while unlocked), and
~/.config/systemd/user/user.slice.d gives it the builds' memory budget. A
process in a scope of TESTS_SLICE, a child of user.slice, gets both, so test
browsers leave the desktop the same room a build does. The memory budget is
one for both: a run beside a build shares it, one more reason for a run to
take the builds lock.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

TESTS_SLICE = 'user-tests.slice'


def in_slice():
    return f'/{TESTS_SLICE}/' in Path('/proc/self/cgroup').read_text()


def enter():
    """Moves this process into a new scope of TESTS_SLICE, unless it is in
    one already; what it starts from then on runs there too. Without the
    user manager (a login over ssh, say) it says so and runs on where it is."""
    if in_slice():
        return
    pid = os.getpid()
    # systemd-run can only start a new command in a scope, and a script read
    # from stdin can't start again: the user manager moves this one in.
    scope = f'oganesson-tests-{pid}-{int(time.time())}.scope'
    properties = [('PIDs', 'au', '1', str(pid)), ('Slice', 's', TESTS_SLICE),
                  # A browser killed for memory fails its test, not the whole run.
                  ('OOMPolicy', 's', 'continue')]
    # A stop or restart of the unit that started the run (the runner's service,
    # an agent's scope) still ends it, as when it was in that unit's cgroup;
    # that unit ending by itself, as an agent's does when it exits, doesn't.
    starter = Path('/proc/self/cgroup').read_text().strip().rsplit('/', 1)[-1]
    if starter.endswith(('.service', '.scope')):
        properties.append(('PartOf', 'as', '1', starter))
    moved = subprocess.run(
        ['busctl', '--user', 'call', 'org.freedesktop.systemd1', '/org/freedesktop/systemd1',
         'org.freedesktop.systemd1.Manager', 'StartTransientUnit', 'ssa(sv)a(sa(sv))',
         scope, 'fail', str(len(properties)), *[part for prop in properties for part in prop],
         '0'],
        capture_output=True, text=True, check=False)
    # The move is a job of the user manager, done a moment after the call.
    deadline = time.monotonic() + 5
    while moved.returncode == 0 and not in_slice() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not in_slice():
        why = moved.stderr.strip() or 'the scope never came'
        print(f'build_slice: running without the build containers\' limits: {why}',
              file=sys.stderr)
