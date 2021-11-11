from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import include, path

User = get_user_model()

urlpatterns = [
    path("admin/", admin.site.urls),
    path("account/", include("django.contrib.auth.urls")),
    path("api/users/", include("authemail.urls")),
    path("api/accounts/", include("src.accounts.urls")),
    path("api/items/", include("src.items.urls")),
    path("api/customers/", include("src.customers.urls")),
    path("scripts/", include("src.scripts.urls")),
    # path('api-auth/', include('rest_framework.urls')), # for web browsable API
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
