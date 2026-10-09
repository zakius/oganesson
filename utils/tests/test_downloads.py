# -*- coding: UTF-8 -*-

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

DOWNLOADS = Path(__file__).resolve().parent.parent / 'downloads.py'


def _unpack(tmp_path, expected=None):
    """Unpacks a cached ZIP configured with the hash of expected, or its own."""
    cache, output = tmp_path / 'cache', tmp_path / 'output'
    cache.mkdir()
    output.mkdir()
    with zipfile.ZipFile(cache / 'a.zip', 'w') as archive:
        archive.writestr('a.txt', 'cached bytes')
    digest = hashlib.sha256(expected or (cache / 'a.zip').read_bytes()).hexdigest()
    config = tmp_path / 'downloads.ini'
    config.write_text('[test]\nurl = https://invalid.example/a.zip\ndownload_filename = a.zip\n'
                      f'output_path = ./\nsha256 = {digest}\n')
    result = subprocess.run(
        [sys.executable,
         str(DOWNLOADS), 'unpack', '-i',
         str(config), '-c',
         str(cache),
         str(output)],
        check=False)
    return result.returncode, output / 'a.txt'


def test_unpack_checks_hashes(tmp_path):
    returncode, extracted = _unpack(tmp_path, b'other bytes')
    assert returncode == 1
    assert not extracted.exists()


def test_unpack_matching_hash(tmp_path):
    returncode, extracted = _unpack(tmp_path)
    assert returncode == 0
    assert extracted.read_text() == 'cached bytes'
