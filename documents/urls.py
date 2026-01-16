from django.urls import path
from .views import SearchView, ReindexView

urlpatterns = [
    path('api/search/', SearchView.as_view(), name='search'),
    path('api/reindex/', ReindexView.as_view(), name='reindex'),
    # Añade más endpoints aquí...
]