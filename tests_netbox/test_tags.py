from dcim.models import Site
from django.test import TestCase
from django.urls import reverse
from ipam.models import Prefix

from netbox_ipam_alt_view.templatetags.ipam_tree import obj_link, obj_url


class TagTest(TestCase):
    def test_obj_url_matches_reverse(self):
        p = Prefix.objects.create(prefix="10.0.0.0/24")
        self.assertEqual(obj_url(p), p.get_absolute_url())
        self.assertEqual(obj_url(p, "edit"), reverse("ipam:prefix_edit", kwargs={"pk": p.pk}))
        self.assertEqual(obj_url(p, "delete"), reverse("ipam:prefix_delete", kwargs={"pk": p.pk}))

    def test_obj_link_escapes(self):
        site = Site.objects.create(name="<b>x</b>", slug="x")
        html = obj_link(site)
        self.assertIn(f'href="{site.get_absolute_url()}"', html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)

    def test_obj_link_none(self):
        self.assertIn("&mdash;", obj_link(None))


class UtilBarTest(TestCase):
    def test_classes_and_label(self):
        from netbox_ipam_alt_view.templatetags.ipam_tree import util_bar

        self.assertIn("bg-success", util_bar(10))
        self.assertIn('<span class="progress-label">10.0%</span>', util_bar(10))
        self.assertIn("bg-warning", util_bar(80))
        self.assertIn("bg-danger", util_bar(95))
        self.assertIn("bg-secondary", util_bar(100))
        self.assertIn(">50.0%</div>", util_bar(50))
        self.assertIn('style="width: 12.5%"', util_bar(12.5))

    def test_none(self):
        from netbox_ipam_alt_view.templatetags.ipam_tree import util_bar

        self.assertEqual(util_bar(None), "")
