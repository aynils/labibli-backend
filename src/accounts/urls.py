from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns
from accounts import views


urlpatterns = [
    path(r'organizations/', views.OrganizationList.as_view()),
    path(r'organizations/<int:pk>/', views.OrganizationDetail.as_view()),
    path(r'users/', views.UserList.as_view()),
    path(r'users/<int:pk>/', views.UserDetail.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)
