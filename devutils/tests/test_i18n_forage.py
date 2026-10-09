# -*- coding: UTF-8 -*-
"""Test i18n_forage.py"""

import sys
import xml.etree.ElementTree as xml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from i18n_forage import stringify_inner_xml # pylint: disable=wrong-import-position
from i18n_lint import validate_placeholders # pylint: disable=wrong-import-position

sys.path.pop(0)

SOURCE = 'Search <ph name="SEARCH_ENGINE">$1<ex>Google</ex></ph> for &amp;'


def test_forage_escapes_and_restores_placeholders():
    node = xml.fromstring('<translation id="1">&amp;Szukaj w <ph name="SEARCH_ENGINE" />'
                          ' &lt;x&gt;</translation>')
    message = stringify_inner_xml(node, SOURCE)
    assert message == ('&amp;Szukaj w <ph name="SEARCH_ENGINE">$1<ex>Google</ex></ph>'
                       ' &lt;x&gt;')
    assert not validate_placeholders(SOURCE, message)


def test_forage_rejects_unknown_placeholders():
    node = xml.fromstring('<translation id="1">A <ph name="OTHER" /></translation>')
    assert stringify_inner_xml(node, SOURCE) is None
