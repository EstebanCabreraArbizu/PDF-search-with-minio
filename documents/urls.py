from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    SearchView, ReindexView, FilterOptionsView, 
    DownloadView, SyncIndexView, PopulateHashesView, IndexStatsView, index
)

urlpatterns = [
    path('', index, name='index'),
    path('api/search/', SearchView.as_view(), name='search'),
    path('api/filter-options/', FilterOptionsView.as_view(), name='filter_options'),
    path('api/download/<path:filename>', DownloadView.as_view(), name='download'),
    path('api/index/sync', SyncIndexView.as_view(), name='sync_index'),
    path('api/index/populate-hashes', PopulateHashesView.as_view(), name='populate_hashes'),
    path('api/index/stats', IndexStatsView.as_view(), name='index_stats'),
    path('api/reindex/', ReindexView.as_view(), name='reindex'),
    
    # Auth
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]