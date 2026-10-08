from django.urls import reverse
from netbox.plugins import PluginTemplateExtension

from .conf import get_setting


class PrefixListTreeButton(PluginTemplateExtension):
    """'Tree view' button on the native prefix list, carrying the current filters over."""

    models = ["ipam.prefix"]

    def list_buttons(self):
        if not get_setting("show_list_toggle"):
            return ""
        query = self.context["request"].GET.urlencode()
        url = reverse("plugins:netbox_ipam_alt_view:tree") + (f"?{query}" if query else "")
        return self.render("netbox_ipam_alt_view/inc/list_button.html", extra_context={"tree_url": url})


template_extensions = [PrefixListTreeButton]
