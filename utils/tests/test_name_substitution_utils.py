# -*- coding: UTF-8 -*-

import xml.etree.ElementTree as xml

from .. import name_substitution_utils as util


def test_xtb_rekeys_translations_without_a_replacement():
    xtb = ('<translationbundle lang="ko">'
           '<translation id="1">Chromium에서는 이 확장 프로그램을 검토할 것을 권장합니다.</translation>'
           '<translation id="2">이 확장 프로그램을 검토하세요.</translation>'
           '<translation id="3">Chromium을 사용하세요</translation>'
           '</translationbundle>')
    result = util.replace_xtb_tree(xtb, {'1': '10', '2': '20'})
    assert result is not None
    translations = xml.fromstring(result).findall('translation')
    assert [t.get('id') for t in translations] == ['10', '20', '3']
    assert translations[0].text.startswith('Chromium에서는')


def test_xtb_unchanged_without_mapped_ids():
    xtb = '<translationbundle><translation id="1">이 확장 프로그램</translation></translationbundle>'
    assert util.replace_xtb_tree(xtb, {'2': '20'}) is None
