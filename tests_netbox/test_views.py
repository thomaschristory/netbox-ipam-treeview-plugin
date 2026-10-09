from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from netbox_ipam_treeview.columns import USER_CONFIG_PATH
from netbox_ipam_treeview.tree.nodes import pfx_key, vrf_key

from .fixtures import make_tree, superuser

NS = "plugins:netbox_ipam_treeview:"


class ViewTest(TestCase):
    def setUp(self):
        self.user = superuser()
        self.client.force_login(self.user)

    def test_tree_page_empty(self):
        r = self.client.get(reverse(NS + "tree"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No prefixes")

    def test_tree_page_roots(self):
        make_tree()
        r = self.client.get(reverse(NS + "tree"))
        self.assertContains(r, 'data-key="vrf:0"')
        self.assertContains(r, "RED")
        self.assertNotContains(r, "10.1.1.0/26")

    def test_children_fragment(self):
        t = make_tree()
        r = self.client.get(reverse(NS + "children"), {"key": pfx_key(t["p24"].pk), "level": "3"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "10.1.1.0/26")
        self.assertContains(r, 'aria-level="5"')  # aria-level = level + 1, children sit at level 4
        self.assertContains(r, "10.1.1.128/25")  # free-space row

    def test_children_unknown_key_404(self):
        r = self.client.get(reverse(NS + "children"), {"key": "pfx:999999", "level": "0"})
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "ipt-error", status_code=404)

    def test_children_bad_key_404(self):
        r = self.client.get(reverse(NS + "children"), {"key": "nope", "level": "x"})
        self.assertEqual(r.status_code, 404)

    def test_subtree_root_and_truncation_header(self):
        make_tree()
        with self.settings(PLUGINS_CONFIG={"netbox_ipam_treeview": {"expand_all_limit": 2}}):
            r = self.client.get(reverse(NS + "subtree"), {"key": "__root__"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("X-Tree-Truncated"), "1")

    def test_expand_endpoint(self):
        t = make_tree()
        r = self.client.get(reverse(NS + "expand"), {"keys": f"{vrf_key(None)},{pfx_key(t['orphan'].pk)}"})
        self.assertContains(r, "10.0.0.0/8")

    def test_filtered_page(self):
        make_tree()
        r = self.client.get(reverse(NS + "tree"), {"q": "10.1.1.0/26"})
        self.assertContains(r, "10.1.1.0/26")
        self.assertContains(r, "ipt-context")

    def test_free_space_toggle_off(self):
        t = make_tree()
        r = self.client.get(reverse(NS + "children"), {"key": pfx_key(t["p24"].pk), "level": "0", "free": "0"})
        self.assertNotContains(r, "10.1.1.128/25")

    def test_columns_saved(self):
        r = self.client.post(reverse(NS + "columns"), {"columns": ["status", "tenant"], "next": reverse(NS + "tree")})
        self.assertEqual(r.status_code, 302)
        self.user.config.refresh_from_db()
        self.assertEqual(self.user.config.get(USER_CONFIG_PATH), ["status", "tenant"])

    def test_columns_rejects_offsite_next(self):
        r = self.client.post(reverse(NS + "columns"), {"columns": ["status"], "next": "https://evil.example/"})
        self.assertEqual(r.headers["Location"], reverse(NS + "tree"))


class PermissionViewTest(TestCase):
    def test_requires_view_prefix(self):
        user = get_user_model().objects.create_user("nobody")
        self.client.force_login(user)
        r = self.client.get(reverse(NS + "tree"))
        # NetBox's own permission-denied page, not an empty 403 body (#2).
        self.assertContains(r, "You do not have permission", status_code=403)

    def test_fragments_require_view_prefix(self):
        user = get_user_model().objects.create_user("nobody")
        self.client.force_login(user)
        for name in ("children", "subtree", "expand"):
            r = self.client.get(reverse(NS + name), {"key": "__root__"})
            self.assertContains(r, "You do not have permission", status_code=403, msg_prefix=name)
        r = self.client.post(reverse(NS + "columns"), {"columns": ["status"]})
        self.assertContains(r, "You do not have permission", status_code=403)

    def test_anonymous_without_permission_redirected(self):
        with self.settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=[]):
            r = self.client.get(reverse(NS + "tree"))
        self.assertEqual(r.status_code, 302)

    @override_settings(LOGIN_REQUIRED=True)
    def test_anonymous_redirected(self):
        r = self.client.get(reverse(NS + "tree"))
        self.assertEqual(r.status_code, 302)


class QueryScalingTest(TestCase):
    def setUp(self):
        self.client.force_login(superuser())

    def _children_queries(self, n):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from ipam.models import Prefix

        parent = Prefix.objects.create(prefix=f"10.{n}.0.0/16", status="container")
        for i in range(n):
            Prefix.objects.create(prefix=f"10.{n}.{i}.0/24")
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(reverse(NS + "children"), {"key": pfx_key(parent.pk), "level": "0"})
        self.assertEqual(r.status_code, 200)
        return len(ctx.captured_queries)

    def test_children_query_count_does_not_grow_with_rows(self):
        self.assertEqual(self._children_queries(3), self._children_queries(30))


class ReviewViewFixesTest(TestCase):
    def setUp(self):
        self.client.force_login(superuser())
        make_tree()

    def test_list_paging_params_do_not_trigger_filtered_mode(self):
        for params in ({"per_page": "50"}, {"sort": "-prefix"}, {"page": "2"}):
            r = self.client.get(reverse(NS + "tree"), params)
            self.assertContains(r, 'data-filtered="0"', msg_prefix=str(params))

    def test_list_button_drops_paging_params(self):
        r = self.client.get(reverse("ipam:prefix_list") + "?status=active&per_page=50&sort=prefix&page=2")
        self.assertContains(r, reverse(NS + "tree") + "?status=active")
        self.assertNotContains(r, reverse(NS + "tree") + "?status=active&amp;per_page")


class AnonymousColumnsTest(TestCase):
    def test_anonymous_columns_post_is_rejected(self):
        with self.settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=["*"]):
            r = self.client.post(reverse(NS + "columns"), {"columns": ["status"]})
        self.assertContains(r, "You do not have permission", status_code=403)

    def test_anonymous_has_no_columns_picker(self):
        with self.settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=["*"]):
            r = self.client.get(reverse(NS + "tree"))
        self.assertNotContains(r, reverse(NS + "columns"))
