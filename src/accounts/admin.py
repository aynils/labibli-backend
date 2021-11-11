from authemail.admin import EmailUserAdmin
from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()


class UserAdmin(EmailUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
