from django.urls import path

from . import views

urlpatterns = [
    path("", views.TreeView.as_view(), name="tree"),
    path("children/", views.NodeChildrenView.as_view(), name="children"),
    path("subtree/", views.NodeSubtreeView.as_view(), name="subtree"),
    path("expand/", views.ExpandView.as_view(), name="expand"),
    path("columns/", views.ColumnsView.as_view(), name="columns"),
]
