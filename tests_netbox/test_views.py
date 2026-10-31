from django.test import override_settings
from django.urls import reverse
from utilities.testing import TestCase

from netbox_ipam_treeview.columns import USER_CONFIG_PATH
from netbox_ipam_treeview.tree.nodes import pfx_key, vrf_key
from netbox_ipam_treeview.version import __version__

from .fixtures import VIEW_PERMISSIONS, make_tree

NS = "plugins:netbox_ipam_treeview:"


class ViewTest(TestCase):
    user_permissions = VIEW_PERMISSIONS

    def test_tree_page_empty(self):
        r = self.client.get(reverse(NS + "tree"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No prefixes")

    def test_static_assets_carry_plugin_version(self):
        r = self.client.get(reverse(NS + "tree"))
        self.assertContains(r, f"netbox_ipam_treeview/tree.js?v={__version__}")
        self.assertContains(r, f"netbox_ipam_treeview/tree.css?v={__version__}")

    def test_tree_page_roots(self):
        make_tree()
        r = self.client.get(reverse(NS + "tree"))
        self.assertContains(r, 'data-key="vrf:0"')
        self.assertContains(r, "RED")
        self.assertNotContains(r, "10.1.1.0/26")
        self.assertContains(r, reverse(NS + "columns"))  # column picker for authenticated users
        self.assertContains(r, 'data-truncated-message="Row limit reached: showing a partial tree.')

    def test_superuser_sees_tree_and_row_actions(self):
        t = make_tree()
        self.user.is_superuser = True
        self.user.save()
        r = self.client.get(reverse(NS + "children"), {"key": pfx_key(t["p24"].pk), "level": "0"})
        self.assertContains(r, "10.1.1.0/26")
        self.assertContains(r, reverse("ipam:prefix_edit", kwargs={"pk": t["p26"].pk}))

    def test_children_fragment(self):
        t = make_tree()
        r = self.client.get(reverse(NS + "children"), {"key": pfx_key(t["p24"].pk), "level": "3"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "10.1.1.0/26")
        self.assertContains(r, 'aria-level="5"')  # aria-level = level + 1, children sit at level 4
        self.assertContains(r, "10.1.1.128/25")  # free-space row

    def test_row_actions_follow_prefix_permissions(self):
        t = make_tree()
        params = {"key": pfx_key(t["p24"].pk), "level": "0"}
        edit_url = reverse("ipam:prefix_edit", kwargs={"pk": t["p26"].pk})
        delete_url = reverse("ipam:prefix_delete", kwargs={"pk": t["p26"].pk})
        add_url = reverse("ipam:prefix_add")
        r = self.client.get(reverse(NS + "children"), params)
        for url in (edit_url, delete_url, add_url):
            self.assertNotContains(r, url)
        self.add_permissions("ipam.add_prefix", "ipam.change_prefix", "ipam.delete_prefix")
        r = self.client.get(reverse(NS + "children"), params)
        for url in (edit_url, delete_url, add_url):
            self.assertContains(r, url)

    def test_children_unknown_key_404(self):
        r = self.client.get(reverse(NS + "children"), {"key": "pfx:999999", "level": "0"})
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "ipt-error", status_code=404)

    def test_error_row_sits_under_the_failed_node(self):
        # tree.js inserts the 404 error row under the node: it needs the child level and the parent key.
        for name in ("children", "subtree"):
            with self.subTest(name):
                r = self.client.get(reverse(NS + name), {"key": "pfx:999999", "level": "3"})
                self.assertContains(r, 'data-level="4"', status_code=404)
                self.assertContains(r, 'data-parent="pfx:999999"', status_code=404)
                self.assertContains(r, "--ipt-level: 4", status_code=404)

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
    # self.user has no permissions; anonymous cases log out first.
    def test_requires_view_prefix(self):
        r = self.client.get(reverse(NS + "tree"))
        # NetBox's own permission-denied page, not an empty 403 body (#2).
        self.assertContains(r, "You do not have permission", status_code=403)

    def test_fragments_require_view_prefix(self):
        for name in ("children", "subtree", "expand"):
            r = self.client.get(reverse(NS + name), {"key": "__root__"})
            self.assertContains(r, "You do not have permission", status_code=403, msg_prefix=name)
        r = self.client.post(reverse(NS + "columns"), {"columns": ["status"]})
        self.assertContains(r, "You do not have permission", status_code=403)

    def test_anonymous_without_permission_redirected(self):
        self.client.logout()
        with self.settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=[]):
            r = self.client.get(reverse(NS + "tree"))
        self.assertEqual(r.status_code, 302)

    @override_settings(LOGIN_REQUIRED=True)
    def test_anonymous_redirected(self):
        self.client.logout()
        r = self.client.get(reverse(NS + "tree"))
        self.assertEqual(r.status_code, 302)

    @override_settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=["ipam.prefix"])
    def test_anonymous_allowed_by_exempt_view_permissions(self):
        self.client.logout()
        make_tree()
        self.assertEqual(self.client.get(reverse(NS + "tree")).status_code, 200)
        self.assertContains(self.client.get(reverse(NS + "subtree"), {"key": "__root__"}), "10.1.1.0/26")

    @override_settings(LOGIN_REQUIRED=True, EXEMPT_VIEW_PERMISSIONS=["ipam.prefix"])
    def test_exempt_view_permissions_do_not_bypass_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse(NS + "tree")).status_code, 302)

    @override_settings(EXEMPT_VIEW_PERMISSIONS=["ipam.prefix"])
    def test_authenticated_user_allowed_by_exempt_view_permissions(self):
        make_tree()
        self.assertEqual(self.client.get(reverse(NS + "tree")).status_code, 200)
        self.assertContains(self.client.get(reverse(NS + "subtree"), {"key": "__root__"}), "10.1.1.0/26")


class QueryScalingTest(TestCase):
    user_permissions = VIEW_PERMISSIONS

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

    def _vrf_children_queries(self, n):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from ipam.models import RIR, Aggregate, Prefix

        rir, _ = RIR.objects.get_or_create(name="R", slug="r")
        for i in range(n):
            Aggregate.objects.create(prefix=f"{100 + n}.{i}.0.0/16", rir=rir)
            Prefix.objects.create(prefix=f"{100 + n}.{i}.0.0/24")
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(reverse(NS + "children"), {"key": vrf_key(None), "level": "0"})
        self.assertContains(r, 'data-key="agg:', count=Aggregate.objects.count())
        return len(ctx.captured_queries)

    def test_aggregate_rows_query_count_does_not_grow_with_rows(self):
        self.assertEqual(self._vrf_children_queries(3), self._vrf_children_queries(30))

    def test_filtered_ancestor_candidates_are_not_loaded_in_full(self):
        # Every container is an ancestor candidate; only the match's ancestors are rendered, so only they are loaded
        # as full rows (#25).
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from ipam.models import Prefix

        for i in range(20):
            Prefix.objects.create(prefix=f"10.{i}.0.0/16", status="container")
            Prefix.objects.create(prefix=f"10.{i}.1.0/24")
        Prefix.objects.create(prefix="172.16.0.0/12", status="container")
        Prefix.objects.create(prefix="172.16.1.0/24", description="needle")
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(reverse(NS + "tree"), {"q": "needle"})
        self.assertContains(r, 'data-filtered="1"')
        self.assertContains(r, "172.16.0.0/12")
        self.assertNotContains(r, "10.3.0.0/16")
        candidates = [q["sql"] for q in ctx.captured_queries if '"_children" > 0' in q["sql"]]
        self.assertTrue(candidates)
        for sql in candidates:
            self.assertNotIn('"description"', sql)
            self.assertNotIn("JOIN", sql)


class AggregateUtilizationViewTest(TestCase):
    """Under a VRF group, an aggregate's utilization counts only that VRF's prefixes (#26)."""

    user_permissions = VIEW_PERMISSIONS

    def setUp(self):
        super().setUp()
        from ipam.models import Prefix

        self.t = make_tree()
        Prefix.objects.create(prefix="10.2.0.0/15", vrf=self.t["red"])
        Prefix.objects.create(prefix="10.8.0.0/16")
        # 10/8 holds 10.1/16 + 10.8/16 in the global table (2/256) and 10.1/16 + 10.2/15 in RED (3/256);
        # across all VRFs their union is 4/256.
        self.global_bar, self.red_bar = 'aria-valuenow="0.78125"', 'aria-valuenow="1.171875"'

    def test_same_aggregate_differs_per_vrf_group(self):
        agg = self.t["agg"].pk
        r = self.client.get(reverse(NS + "children"), {"key": vrf_key(None), "level": "0"})
        self.assertContains(r, f'data-key="agg:{agg}@0"')
        self.assertContains(r, self.global_bar)
        self.assertNotContains(r, self.red_bar)
        r = self.client.get(reverse(NS + "children"), {"key": vrf_key(self.t["red"].pk), "level": "0"})
        self.assertContains(r, f'data-key="agg:{agg}@{self.t["red"].pk}"')
        self.assertContains(r, self.red_bar)
        self.assertNotContains(r, self.global_bar)

    def test_aggregate_tab_rows_are_per_vrf(self):
        r = self.client.get(reverse("ipam:aggregate_tree", kwargs={"pk": self.t["agg"].pk}))
        self.assertContains(r, self.global_bar)
        self.assertContains(r, self.red_bar)

    def test_ungrouped_tree_keeps_netbox_number(self):
        with self.settings(PLUGINS_CONFIG={"netbox_ipam_treeview": {"group_by_vrf": False}}):
            r = self.client.get(reverse(NS + "tree"))
        self.assertContains(r, f'data-key="agg:{self.t["agg"].pk}@*"')
        self.t["agg"].refresh_from_db()  # created from a string; get_utilization() needs an IPNetwork
        self.assertEqual(self.t["agg"].get_utilization(), 1.5625)
        self.assertContains(r, 'aria-valuenow="1.5625"')
        self.assertNotContains(r, self.global_bar)
        self.assertNotContains(r, self.red_bar)


class ConstrainedAggregateUtilizationViewTest(TestCase):
    """A constrained user's aggregate bar counts only the prefixes that user can see (#26 review)."""

    user_permissions = ("ipam.view_aggregate", "ipam.view_vrf")

    def setUp(self):
        super().setUp()
        from django.contrib.contenttypes.models import ContentType
        from ipam.models import Prefix
        from users.models import ObjectPermission

        self.t = make_tree()
        Prefix.objects.create(prefix="10.2.0.0/15", vrf=self.t["red"])  # hidden from the user
        perm = ObjectPermission.objects.create(
            name="view one prefix", actions=["view"], constraints={"prefix__net_contained_or_equal": "10.1.9.0/24"}
        )
        perm.object_types.add(ContentType.objects.get_for_model(Prefix))
        perm.users.add(self.user)

    def test_hidden_vrf_prefixes_not_counted(self):
        r = self.client.get(reverse(NS + "children"), {"key": vrf_key(self.t["red"].pk), "level": "0"})
        self.assertContains(r, f'data-key="agg:{self.t["agg"].pk}@{self.t["red"].pk}"')
        self.assertContains(r, f'aria-valuenow="{100 / 65536}"')  # only 10.1.9.0/24 of 10/8
        self.assertNotContains(r, 'aria-valuenow="1.171875"')  # RED's 10.1/16 + 10.2/15, both hidden


class ReviewViewFixesTest(TestCase):
    user_permissions = VIEW_PERMISSIONS

    def setUp(self):
        super().setUp()
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
    def setUp(self):
        super().setUp()
        self.client.logout()

    def test_anonymous_columns_post_is_rejected(self):
        with self.settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=["*"]):
            r = self.client.post(reverse(NS + "columns"), {"columns": ["status"]})
        self.assertContains(r, "You do not have permission", status_code=403)

    def test_anonymous_has_no_columns_picker(self):
        with self.settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=["*"]):
            r = self.client.get(reverse(NS + "tree"))
        self.assertNotContains(r, reverse(NS + "columns"))
