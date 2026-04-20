from django.urls import path

from .views import (
    ConstanciasV2SearchView,
    DocumentDownloadV2View,
    FilterOptionsV2View,
    SegurosV2SearchView,
    TRegistroV2SearchView,
)


urlpatterns = [
    path("filter-options", FilterOptionsV2View.as_view(), name="v2_filter_options"),
    path("search/seguros", SegurosV2SearchView.as_view(), name="v2_search_seguros"),
    path("search/tregistro", TRegistroV2SearchView.as_view(), name="v2_search_tregistro"),
    path("search/constancias", ConstanciasV2SearchView.as_view(), name="v2_search_constancias"),
    path("documents/<uuid:document_id>/download", DocumentDownloadV2View.as_view(), name="v2_document_download"),
]
