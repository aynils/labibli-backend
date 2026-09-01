from authemail.admin import EmailUserAdmin
from django.contrib import admin
from django.contrib.auth import get_user_model

from src.accounts.models import Organization

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


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """L'endroit où les rappels s'allument, une bibliothèque à la fois.

    L'organisation n'était pas dans l'admin : allumer les rappels demandait un
    shell sur la production. Une case à cocher se relit ; une ligne d'ORM tapée
    dans un shell, non — et c'est sur cette ligne-là qu'on oublie le `filter`.

    🔑 Les deux interrupteurs portent des `verbose_name` explicites (voir
    `Organization`), parce que c'est ICI, en colonnes côte à côte, qu'on
    décidera lequel cocher. « Rappels » deux fois de suite ferait cocher le
    mauvais, et le mauvais écrit à des gens qui ne sont pas nos clients.
    """

    list_display = (
        "id",
        "name",
        "is_active",
        "member_reminders_enabled",
        "librarian_digest_enabled",
        "reminder_schedule_days",
    )
    list_filter = ("is_active", "member_reminders_enabled", "librarian_digest_enabled")
    list_editable = (
        "member_reminders_enabled",
        "librarian_digest_enabled",
        "reminder_schedule_days",
    )
    search_fields = ("name",)
