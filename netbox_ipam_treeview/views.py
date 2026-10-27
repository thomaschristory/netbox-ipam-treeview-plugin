from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View
from ipam.filtersets import PrefixFilterSet
from ipam.forms import PrefixFilterForm
from ipam.models import VRF, Aggregate, Prefix
from netbox.views import generic
from utilities.views import ContentTypePermissionRequiredMixin, ViewTab, register_model_view

from .columns import COLUMNS, USER_CONFIG_PATH, resolve_columns
from .conf import FREE_COOKIE, free_preference, get_setting
from .tree.builder import NodeNotFound, TreeBuilder
from .tree.nodes import tab_key
from .utilization import bulk_aggregate_utilization, bulk_utilization

# List-view parameters (paging, sorting, export) that are not filters; the list's "Tree view" button drops them too.
LIST_ONLY_PARAMS = {"page", "per_page", "sort", "ordering", "export"}


def _free(request):
    return free_preference(request.GET.get("free"), request.COOKIES.get(FREE_COOKIE), get_setting("show_free_space"))


def _level(request):
    try:
        return max(0, min(int(request.GET.get("level", 0)), 128))
    except ValueError:
        return 0


def table_context(request, builder, nodes, **extra):
    """Context shared by the tree page, fragment responses and detail tabs."""
    columns = resolve_columns(request.user)
    if "utilization" in columns:
        values = bulk_utilization([n.obj for n in nodes if n.kind == "prefix"])
        # Under a VRF group an aggregate counts that VRF's prefixes only; ungrouped (ALL_VRFS) it is NetBox's number.
        agg_values = bulk_aggregate_utilization([(n.obj, n.vrf_id) for n in nodes if n.kind == "aggregate"])
        for n in nodes:
            if n.kind == "prefix":
                n.utilization = values.get(n.obj.pk)
            elif n.kind == "aggregate":
                n.utilization = agg_values.get((n.obj.pk, n.vrf_id))
    return {
        "nodes": nodes,
        "columns": columns,
        "column_headers": [(c, COLUMNS[c]) for c in columns],
        "all_columns": COLUMNS,
        "prefix_add_url": reverse("ipam:prefix_add"),
        "tree_perms": {a: request.user.has_perm(f"ipam.{a}_prefix") for a in ("add", "change", "delete")},
        "free": builder.show_free_space,
        "filtered": False,
        "truncated": builder.truncated,
        "limit": builder.limit,
        # Fragments are fetched from the tree page; links in them should return there, not to the fragment URL.
        "return_url": request.headers.get("X-Tree-Page") or request.get_full_path(),
        **extra,
    }


def filter_querystring(params):
    """The querystring without list-only parameters (page, sorting, export)."""
    params = params.copy()
    for key in LIST_ONLY_PARAMS:
        params.pop(key, None)
    return params.urlencode()


class TreeAccessMixin(ContentTypePermissionRequiredMixin):
    # NetBox's mixin enforces LOGIN_REQUIRED and the model permission. handle_no_permission() redirects anonymous
    # users to login and raises PermissionDenied for authenticated ones, so NetBox renders its own 403 page. tree.js
    # treats a 403 fragment as a failed load and reloads the page when a fragment request was redirected to login.
    def get_required_permission(self):
        return "ipam.view_prefix"

    def builder(self, request):
        return TreeBuilder(request.user, show_free_space=_free(request))

    def rows(self, request, builder, nodes):
        response = render(request, "netbox_ipam_treeview/inc/rows.html", table_context(request, builder, nodes))
        if builder.truncated:
            response["X-Tree-Truncated"] = "1"
        return response

    def not_found(self, request):
        # tree.js shows this row under the node that failed to load (e.g. a prefix deleted since the page loaded).
        context = {"error": True, "parent_key": request.GET.get("key", ""), "level": _level(request) + 1}
        return render(request, "netbox_ipam_treeview/inc/rows.html", context, status=404)


class TreeView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        filterset = PrefixFilterSet(request.GET, queryset=builder.prefixes)
        # Only parameters the prefix filterset understands put the tree in filtered mode.
        filter_params = {k for k, v in request.GET.lists() if k in filterset.filters and any(v)}
        filtered = bool(filter_params) and filterset.is_valid()
        nodes = builder.filtered(filterset.qs) if filtered else builder.roots()
        context = table_context(
            request,
            builder,
            nodes,
            filtered=filtered,
            filter_form=PrefixFilterForm(request.GET, label_suffix=""),
            model=Prefix,
            list_querystring=request.GET.urlencode(),
            storage_key="ipam-tree:page",
            root_key="__root__",
        )
        return render(request, "netbox_ipam_treeview/tree.html", context)


class NodeChildrenView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        try:
            nodes = builder.children(request.GET.get("key", ""), _level(request))
        except NodeNotFound:
            return self.not_found(request)
        return self.rows(request, builder, nodes)


class NodeSubtreeView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        key = request.GET.get("key", "")
        try:
            nodes = builder.full_tree() if key == "__root__" else builder.subtree(key, _level(request))
        except NodeNotFound:
            return self.not_found(request)
        return self.rows(request, builder, nodes)


class ExpandView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        keys = [k for k in request.GET.get("keys", "").split(",") if k]
        tab = request.GET.get("tab")
        try:
            # A detail tab restores its own tree, rooted at its object, instead of the page's.
            roots = builder.tab_roots(tab) if tab else None
        except NodeNotFound:
            return self.not_found(request)
        # all=1 restores "Expand all": every node within the row budget, as subtree/?key=__root__ does on the page.
        nodes = builder.full_tree(roots) if request.GET.get("all") == "1" else builder.expand(keys, roots)
        return self.rows(request, builder, nodes)


class ColumnsView(TreeAccessMixin, View):
    def post(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied  # anonymous users (LOGIN_REQUIRED=False) have no stored preferences
        columns = [c for c in request.POST.getlist("columns") if c in COLUMNS]
        request.user.config.set(USER_CONFIG_PATH, columns or None, commit=True)
        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse("plugins:netbox_ipam_treeview:tree")
        return HttpResponseRedirect(next_url)


#
# Tree tabs on core object views
#


class _TreeTab(generic.ObjectView):
    template_name = "netbox_ipam_treeview/tab.html"
    base_template = "generic/object.html"
    setting = None

    def get(self, request, *args, **kwargs):
        if not get_setting(self.setting):
            raise Http404
        return super().get(request, *args, **kwargs)

    def tree_roots(self, builder, instance):
        """The top rows of this object's tree."""
        return builder.object_roots(instance)

    def get_extra_context(self, request, instance):
        builder = TreeBuilder(request.user, show_free_space=_free(request))
        try:
            roots = self.tree_roots(builder, instance)
        except NodeNotFound:
            roots = []
        # A single root opens with its children; several (an aggregate in more than one VRF) start collapsed.
        nodes, root_key = _expanded(builder, roots[0]) if len(roots) == 1 else (roots, "__root__")
        tab = tab_key(instance._meta.model_name, instance.pk)
        return table_context(
            request,
            builder,
            nodes,
            base_template=self.base_template,
            root_key=root_key,
            # tree.js restores the saved state through the expand endpoint, rooted at this object. Not named `tab`:
            # NetBox's ObjectView passes its ViewTab under that name for the tab bar.
            tree_tab=tab,
            storage_key=f"ipam-tree:{tab}",
        )


def _tab(setting):
    return ViewTab(label=_("Tree"), permission="ipam.view_prefix", weight=450, visible=lambda obj: get_setting(setting))


def _expanded(builder, root):
    """The root and its children, with aggregate children opened too so prefixes are visible at once."""
    kids = builder.children(root.key, root.level) if root.has_children else []
    root.expanded = bool(kids)
    nodes = [root]
    for kid in kids:
        nodes.append(kid)
        if kid.kind == "aggregate":
            grandkids = builder.children(kid.key, kid.level)
            kid.expanded = bool(grandkids)
            nodes += grandkids
    return nodes, root.key


@register_model_view(Prefix, "tree", path="tree")
class PrefixTreeTab(_TreeTab):
    queryset = Prefix.objects.all()
    base_template = "ipam/prefix/base.html"
    setting = "show_prefix_tab"
    tab = _tab("show_prefix_tab")

    def tree_roots(self, builder, instance):
        # Through the builder's queryset: it carries the related objects the row columns show.
        return builder.object_roots(builder._get_prefix(instance.pk))


@register_model_view(Aggregate, "tree", path="tree")
class AggregateTreeTab(_TreeTab):
    queryset = Aggregate.objects.all()
    setting = "show_aggregate_tab"
    tab = _tab("show_aggregate_tab")


@register_model_view(VRF, "tree", path="tree")
class VRFTreeTab(_TreeTab):
    queryset = VRF.objects.all()
    setting = "show_vrf_tab"
    tab = _tab("show_vrf_tab")
