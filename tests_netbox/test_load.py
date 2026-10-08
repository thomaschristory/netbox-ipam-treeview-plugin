from django.conf import settings
from django.test import SimpleTestCase

from netbox_ipam_treeview.conf import get_setting


class PluginLoadTest(SimpleTestCase):
    def test_plugin_installed(self):
        self.assertIn("netbox_ipam_treeview", settings.PLUGINS)

    def test_defaults(self):
        self.assertEqual(get_setting("expand_all_limit"), 5000)
