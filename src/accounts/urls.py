from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from src.accounts import views

urlpatterns = [
    path(
        r"organizations/", views.OrganizationCreate.as_view(), name="post_organizations"
    ),
    path(
        r"organizations/<int:pk>/",
        views.OrganizationDetail.as_view(),
        name="get_put_patch_delete_organizations",
    ),
    path(
        r"organization/",
        views.OrganizationCurrent.as_view(),
        name="get_current_organization",
    ),
    path(r"users/", views.UserList.as_view()),
    path(r"users/<int:pk>/", views.UserDetail.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)
