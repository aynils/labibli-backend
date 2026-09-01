from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from src.accounts import views as accounts_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("account/", include("django.contrib.auth.urls")),
    # ⚠️ AVANT l'include d'authemail, et l'ordre est ce qui fait tout : Django
    # résout dans l'ordre de la liste, donc cette route-ci l'emporte sur celle
    # que « authemail.urls » déclare au même chemin. La déplacer plus bas la
    # rendrait inopérante, en silence.
    path("api/users/signup/", accounts_views.SignupAvecOrganisation.as_view(), name="signup"),
    path("api/users/", include("authemail.urls")),
    path("api/accounts/", include("src.accounts.urls")),
    path("api/items/", include("src.items.urls")),
    path("api/customers/", include("src.customers.urls")),
    path("api/payment/", include("src.payment.urls")),
    path("scripts/", include("src.scripts.urls")),
    # path('api-auth/', include('rest_framework.urls')), # for web browsable API
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
