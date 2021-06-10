from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)

from lessons.views import get_lessons, get_lesson, get_categories, post_picture
from users.views import signup
from kpma.settings import MEDIA_ROOT, MEDIA_URL

User = get_user_model()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('account/', include('django.contrib.auth.urls')),
    path('account/signup', signup, name="signup"),
    path('api-auth/', include('rest_framework.urls')),
    path('api/categories/', get_categories),
    path('api/lessons/<str:category>', get_lessons),
    path('api/lesson/<str:lesson_id>', get_lesson),
    path('api/picture/', post_picture),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
]

urlpatterns += static(MEDIA_URL, document_root=MEDIA_ROOT)
