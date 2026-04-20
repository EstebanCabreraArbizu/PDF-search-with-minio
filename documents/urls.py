from django.urls import path
from .views import (
    SearchView, ReindexView, FilterOptionsView, 
    DownloadView, SyncIndexView, PopulateHashesView, IndexStatsView, index,
    seguros_ui, tregistro_ui,
    FilesListView, FilesClassifyPreviewView, FilesUploadView, CreateFolderView, FilesDeleteView, FoldersListView,
    BulkSearchView, MergePdfsView, CurrentUserView, HealthCheckView
)
from .auth_views import AuthLoginView, AuthLogoutView
from .ui_views import login_ui, constancias_ui

urlpatterns = [
    path('', login_ui, name='index'),
    path('legacy/', index, name='legacy_index'),
    path('ui/login/', login_ui, name='login_ui'),
    path('ui/seguros/', seguros_ui, name='search_seguros_ui'),
    path('ui/tregistro/', tregistro_ui, name='search_tregistro_ui'),
    path('ui/constancias/', constancias_ui, name='search_constancias_ui'),
    path('api/auth/login/', AuthLoginView.as_view(), name='auth_login'),
    path('api/auth/logout/', AuthLogoutView.as_view(), name='auth_logout'),
    path('api/search', SearchView.as_view(), name='search'),
    path('api/search/bulk', BulkSearchView.as_view(), name='bulk_search'),
    path('api/filter-options', FilterOptionsView.as_view(), name='filter_options'),
    path('api/merge-pdfs', MergePdfsView.as_view(), name='merge_pdfs'),
    path('api/download/<path:filename>', DownloadView.as_view(), name='download'),
    path('api/index/sync', SyncIndexView.as_view(), name='sync_index'),
    path('api/index/populate-hashes', PopulateHashesView.as_view(), name='populate_hashes'),
    path('api/index/stats', IndexStatsView.as_view(), name='index_stats'),
    path('api/reindex', ReindexView.as_view(), name='reindex'),
    
    # User/Health Endpoints
    path('api/me', CurrentUserView.as_view(), name='current_user'),
    path('health', HealthCheckView.as_view(), name='health_check'),
    
    # File Management (migrated from Flask)
    path('api/files/list', FilesListView.as_view(), name='files_list'),
    path('api/files/classify-preview', FilesClassifyPreviewView.as_view(), name='files_classify_preview'),
    path('api/files/upload', FilesUploadView.as_view(), name='files_upload'),
    path('api/files/create-folder', CreateFolderView.as_view(), name='create_folder'),
    path('api/files/delete', FilesDeleteView.as_view(), name='files_delete'),
    path('api/folders', FoldersListView.as_view(), name='folders_list'),
]