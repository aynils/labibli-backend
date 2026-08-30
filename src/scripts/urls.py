from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from src.scripts import views

urlpatterns = [
    path(r"import/", views.ImportFromFile.as_view(), name="import_file"),
]

urlpatterns = format_suffix_patterns(urlpatterns)
