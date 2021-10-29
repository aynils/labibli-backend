from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from customers import views

urlpatterns = [
    path(r'', views.CustomersList.as_view(), name="list_post_customer"),
    path(r'<int:pk>/', views.CustomerDetail.as_view(), name="get_put_patch_delete_customer"),
]

urlpatterns = format_suffix_patterns(urlpatterns)
