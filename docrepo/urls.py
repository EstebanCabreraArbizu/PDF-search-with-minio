from django.urls import path

from .views import ConstanciasV2SearchView, SegurosV2SearchView, TRegistroV2SearchView


urlpatterns = [
    path("search/seguros", SegurosV2SearchView.as_view(), name="v2_search_seguros"),
    path("search/tregistro", TRegistroV2SearchView.as_view(), name="v2_search_tregistro"),
    path("search/constancias", ConstanciasV2SearchView.as_view(), name="v2_search_constancias"),
]
