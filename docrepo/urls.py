from django.urls import path

from .views import (
    ConstanciasV2SearchView,
    DocumentDownloadV2View,
    DocumentsZipDownloadV2View,
    FilterOptionsV2View,
    SegurosV2SearchView,
    TRegistroV2SearchView,
)


urlpatterns = [
    path("filter-options", FilterOptionsV2View.as_view(), name="v2_filter_options"),
    path("seguros/search/", SegurosV2SearchView.as_view(), name="v2_search_seguros"),
    path("seguros/search/legacy/", SegurosV2SearchView.as_view(), name="v2_search_seguros_legacy"),
    path("tregistro/search/", TRegistroV2SearchView.as_view(), name="v2_search_tregistro"),
    path("tregistro/search/legacy/", TRegistroV2SearchView.as_view(), name="v2_search_tregistro_legacy"),
    path("constancias/search/", ConstanciasV2SearchView.as_view(), name="v2_search_constancias"),
    path("constancias/search/legacy/", ConstanciasV2SearchView.as_view(), name="v2_search_constancias_legacy"),
    path("documents/download-zip", DocumentsZipDownloadV2View.as_view(), name="v2_documents_download_zip"),
    path("documents/<uuid:document_id>/download", DocumentDownloadV2View.as_view(), name="v2_document_download"),
]
