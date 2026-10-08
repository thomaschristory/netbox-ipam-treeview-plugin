from django.conf import settings
from django.contrib.auth.mixins import AccessMixin
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View
from ipam.filtersets import PrefixFilterSet
from ipam.forms import PrefixFilterForm
from ipam.models import VRF, Aggregate, Prefix
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from .columns import COLUMNS, USER_CONFIG_PATH, resolve_columns
from .conf import get_setting
from .tree.builder import NodeNotFound, TreeBuilder
from .utilization import bulk_utilization

# Query parameters that belong to the tree itself, not to the prefix filterset.
OWN_PARAMS = {"free", "key", "level", "keys"}


def _free(request):
    raw = request.GET.get("free")
    return get_setting("show_free_space") if raw is None else raw == "1"


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
        for n in nodes:
            if n.kind == "prefix":
                n.utilization = values.get(n.obj.pk)
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


class TreeAccessMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated and settings.LOGIN_REQUIRED:
            return self.handle_no_permission()
        if not request.user.has_perm("ipam.view_prefix"):
            return HttpResponseForbidden() if request.user.is_authenticated else self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def builder(self, request):
        return TreeBuilder(request.user, show_free_space=_free(request))

    def rows(self, request, builder, nodes):
        response = render(request, "netbox_ipam_alt_view/inc/rows.html", table_context(request, builder, nodes))
        if builder.truncated:
            response["X-Tree-Truncated"] = "1"
        return response

    def not_found(self, request):
        return render(request, "netbox_ipam_alt_view/inc/rows.html", {"error": True}, status=404)


class TreeView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        filter_params = {k for k, v in request.GET.lists() if k not in OWN_PARAMS and any(v)}
        filterset = PrefixFilterSet(request.GET, queryset=builder.prefixes)
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
        return render(request, "netbox_ipam_alt_view/tree.html", context)


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
        keys = {k for k in request.GET.get("keys", "").split(",") if k}
        return self.rows(request, builder, builder.expand(keys))


class ColumnsView(TreeAccessMixin, View):
    def post(self, request):
        columns = [c for c in request.POST.getlist("columns") if c in COLUMNS]
        request.user.config.set(USER_CONFIG_PATH, columns or None, commit=True)
        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse("plugins:netbox_ipam_alt_view:tree")
        return HttpResponseRedirect(next_url)


#
# Tree tabs on core object views
#


class _TreeTab(generic.ObjectView):
    template_name = "netbox_ipam_alt_view/tab.html"
    base_template = "generic/object.html"
    setting = None

    def get(self, request, *args, **kwargs):
        if not get_setting(self.setting):
            raise Http404
        return super().get(request, *args, **kwargs)

    def tree_nodes(self, builder, instance):
        """Return (nodes, root_key) for this object's tree."""
        raise NotImplementedError

    def get_extra_context(self, request, instance):
        builder = TreeBuilder(request.user, show_free_space=_free(request))
        try:
            nodes, root_key = self.tree_nodes(builder, instance)
        except NodeNotFound:
            nodes, root_key = [], "__root__"
        return table_context(
            request,
            builder,
            nodes,
            base_template=self.base_template,
            root_key=root_key,
            storage_key=f"ipam-tree:{instance._meta.model_name}:{instance.pk}",
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

    def tree_nodes(self, builder, instance):
        return _expanded(builder, builder.node_for(builder._get_prefix(instance.pk)))


@register_model_view(Aggregate, "tree", path="tree")
class AggregateTreeTab(_TreeTab):
    queryset = Aggregate.objects.all()
    setting = "show_aggregate_tab"
    tab = _tab("show_aggregate_tab")

    def tree_nodes(self, builder, instance):
        roots = builder.aggregate_roots(instance)
        if len(roots) == 1:
            return _expanded(builder, roots[0])
        return roots, "__root__"


@register_model_view(VRF, "tree", path="tree")
class VRFTreeTab(_TreeTab):
    queryset = VRF.objects.all()
    setting = "show_vrf_tab"
    tab = _tab("show_vrf_tab")

    def tree_nodes(self, builder, instance):
        return _expanded(builder, builder.node_for(instance))
