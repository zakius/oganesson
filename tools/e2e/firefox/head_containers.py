"""Firefox's ContextualIdentityService, as the ports of its containers tests
use it. This browser's containers are the user's list in Settings (the pref
containers.list), and a container's userContextId is its id there, so its
cookieStoreId is firefox-container-<id>. Firefox's site associations ("always
open this site in this container") are Traffic Control's rules for one site
(containers.traffic_control). A test changes them on
chrome://settings/containers, as the user does there."""

import json

from harness import wait_for


def get_pref(test, name):
    """The value of the Settings pref `name`."""
    page = test.browser.new_tab('chrome://settings/containers')
    try:
        wait_for(lambda: page.eval('!!chrome.settingsPrivate'), what='Settings')
        return page.eval(f'chrome.settingsPrivate.getPref({json.dumps(name)}).then(p => p.value)')
    finally:
        test.browser.close_target(page)


def set_pref(test, name, value):
    """Sets the Settings pref `name` to `value`."""
    page = test.browser.new_tab('chrome://settings/containers')
    try:
        wait_for(lambda: page.eval('!!chrome.settingsPrivate'), what='Settings')
        page.eval(f'chrome.settingsPrivate.setPref({json.dumps(name)}, {json.dumps(value)})')
    finally:
        test.browser.close_target(page)


def create(test, container_id, name, icon, color):
    """ContextualIdentityService.create(name, icon, color): the user adds a
    container, here with the id `container_id`."""
    containers = get_pref(test, 'containers.list')
    containers.append({'id': container_id, 'name': name, 'icon': icon, 'color': color})
    set_pref(test, 'containers.list', containers)


def remove(test, container_id):
    """ContextualIdentityService.remove(userContextId): the user deletes the
    container."""
    containers = get_pref(test, 'containers.list')
    kept = [container for container in containers if container['id'] != container_id]
    set_pref(test, 'containers.list', kept)


def set_site_association(test, site, container_id):
    """ContextualIdentityService.setSiteAssociation(site, userContextId): a
    Traffic Control rule that opens `site` in the container."""
    rules = get_pref(test, 'containers.traffic_control')
    rules.append({'url_filter': site, 'container': container_id, 'enabled': True})
    set_pref(test, 'containers.traffic_control', rules)


def remove_site_association(test, site):
    """ContextualIdentityService.removeSiteAssociation(site): the rule for
    `site` goes."""
    rules = get_pref(test, 'containers.traffic_control')
    kept = [rule for rule in rules if rule['url_filter'] != site]
    set_pref(test, 'containers.traffic_control', kept)
