from django.urls import path, include
from rest_framework import routers
from rest_framework.urlpatterns import format_suffix_patterns
from accounts import views

# router = routers.DefaultRouter()
# router.register(r'organizations', views.OrganizationViewSet.as_view())
# router.register(r'users', accounts.views.UserViewSet)

urlpatterns = [
    path(r'organizations/', views.OrganizationList.as_view()),
    path(r'organizations/<int:pk>/', views.OrganizationDetail.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)
