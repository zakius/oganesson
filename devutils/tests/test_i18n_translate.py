# -*- coding: UTF-8 -*-
"""Test i18n_translate.py"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import i18n_translate as translate # pylint: disable=wrong-import-position

sys.path.pop(0)

NAME = 'IDS_SETTINGS_HELIUM_SERVICES_UPDATE'


def _save(tmp_path, monkeypatch, messages):
    source = [{'name': NAME, 'context': '', 'message': message}
              for message in ('Allow automatic browser updates',
                              'Allow automatic component updates')]
    _, dedup_map = translate.build_payload(source, [0, 1], {})
    raw = json.dumps([{'name': NAME, 'message': message} for message in messages])
    response = translate.parse_response(raw, {NAME})
    monkeypatch.setattr(translate, 'TRANSLATIONS_DIR', tmp_path)
    existing = {}
    translate.save_translations('test', source, existing, response, dedup_map)
    return existing


def test_save_rejects_missing_variant(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        _save(tmp_path, monkeypatch, ['A'])
    assert not (tmp_path / 'test.json').exists()


def test_save_both_variants(tmp_path, monkeypatch):
    assert len(_save(tmp_path, monkeypatch, ['A', 'B'])) == 2
