from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from items import views

urlpatterns = [
    path(r'books/', views.BooksList.as_view(), name="get_post_books"),
    path(r'books/<int:pk>/', views.BookDetail.as_view(), name="get_put_patch_delete_book"),
    # path(r'categories/', views.CategoriesList.as_view()),
    # path(r'categories/<int:pk>/', views.CategoryDetail.as_view()),
    path(r'collections/<int:pk>/', views.CollectionDetail.as_view(), name="get_put_patch_delete_collection"),
    path(r'lendings/<int:pk>/', views.LendingDetail.as_view(), name="get_put_patch_delete_lending"),
    path(r'lendings/', views.LendingsList.as_view(), name="list_lending"),
]

urlpatterns = format_suffix_patterns(urlpatterns)