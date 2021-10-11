from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from customers import views

urlpatterns = [
    path(r'categories/', views.CustomersList.as_view(), name = "list_customer"),
    path(r'categories/<int:pk>/', views.CustomerDetail.as_view(), name = "get_put_patch_delete_customer"),
]

urlpatterns = format_suffix_patterns(urlpatterns)
