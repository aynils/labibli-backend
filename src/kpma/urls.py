from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)

from lessons.views import get_lessons, get_lesson
from users.views import signup

User = get_user_model()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('account/', include('django.contrib.auth.urls')),
    path('account/signup', signup, name="signup"),
    path('api-auth/', include('rest_framework.urls')),
    path('api/lessons/', get_lessons),
    path('api/lesson/', get_lesson),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
]
