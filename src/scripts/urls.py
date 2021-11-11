from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from src.scripts import views

urlpatterns = [
    path(r"import/", views.ImportFromV1.as_view(), name="import_from_v1"),
]

urlpatterns = format_suffix_patterns(urlpatterns)
