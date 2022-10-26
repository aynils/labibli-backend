from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from src.scripts import views

urlpatterns = [
    path(r"import/", views.ImportBooksFromISBNS.as_view(), name="import_books"),
]

urlpatterns = format_suffix_patterns(urlpatterns)
