# -*- coding: UTF-8 -*-

# Copyright (c) 2020 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE.ungoogled_chromium file.

from pathlib import Path
import os
import shutil

import pytest

from .. import patches


def test_find_and_check_patch():
    assert isinstance(patches.find_and_check_patch(), Path)

    with pytest.raises(ValueError):
        patches.find_and_check_patch(patch_bin_path=Path('/this/should/not/exist'))

    with pytest.raises(RuntimeError):
        # Use command "false" to return non-zero exit code
        patches.find_and_check_patch(patch_bin_path=Path('/bin/false'))


def test_patch_from_which():
    # We assume GNU patch is already installed to PATH
    assert patches._find_patch_from_which()


def test_patch_from_env():
    os.environ['PATCH_BIN'] = 'patch'
    assert patches._find_patch_from_env() == Path(shutil.which('patch'))

    os.environ['PATCH_BIN'] = shutil.which('patch')
    assert patches._find_patch_from_env() == Path(shutil.which('patch'))

    del os.environ['PATCH_BIN']
    assert patches._find_patch_from_env() is None


def test_merge_patches(tmp_path):
    for name in ('first', 'second', 'other'):
        (tmp_path / name).mkdir()
        patch = 'other.patch' if name == 'other' else 'same.patch'
        (tmp_path / name / 'series').write_text(f'{patch}\n')
        (tmp_path / name / patch).write_text(name)

    with pytest.raises(FileExistsError):
        patches.merge_patches([tmp_path / 'first', tmp_path / 'second'], tmp_path / 'merged')
    assert not (tmp_path / 'merged').exists()

    patches.merge_patches([tmp_path / 'first', tmp_path / 'other'], tmp_path / 'merged')
    assert (tmp_path / 'merged/series').read_text() == 'same.patch\nother.patch'

    with pytest.raises(FileExistsError):
        patches.merge_patches([tmp_path / 'second'], tmp_path / 'merged', prepend=True)
    assert (tmp_path / 'merged/same.patch').read_text() == 'first'
