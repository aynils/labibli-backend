from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import path, include

from labibli.settings import MEDIA_ROOT, MEDIA_URL

User = get_user_model()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('authemail.urls')),
    path('api/accounts/', include('accounts.urls')),
    path('api/items/', include('items.urls')),
    path('api/customers/', include('customers.urls')),
    path('api-auth/', include('rest_framework.urls')), # for web browsable API
]

urlpatterns += static(MEDIA_URL, document_root=MEDIA_ROOT)
