from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from items import views

urlpatterns = [
    path(r'books/', views.BooksList.as_view(), name="list_post_books"),
    path(r'books/<int:pk>/', views.BookDetail.as_view(), name="get_put_patch_delete_book"),
    path(r'books/lookup/', views.book_lookup, name="get_book_details"),
    path(r'books/image/', views.fetch_image, name="get_picture_file"),
    path(r'categories/', views.CategoriesList.as_view(), name="list_post_category"),
    path(r'categories/<int:pk>/', views.CategoryDetail.as_view(), name="get_put_patch_delete_category"),
    path(r'categories/', views.CollectionsList.as_view(), name="list_post_collection"),
    path(r'collections/<int:pk>/', views.CollectionDetail.as_view(), name="get_put_patch_delete_collection"),
    path(r'lendings/<int:pk>/', views.LendingDetail.as_view(), name="get_put_patch_delete_lending"),
    path(r'lendings/<int:pk>/return/', views.ReturnLending.as_view(), name="return_lending"),
    path(r'lendings/', views.LendingsList.as_view(), name="list_post_lending"),
]

urlpatterns = format_suffix_patterns(urlpatterns)
