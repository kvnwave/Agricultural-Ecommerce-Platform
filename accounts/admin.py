from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Profile, UsernameHistory, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0


class UsernameHistoryInline(admin.TabularInline):
    model = UsernameHistory
    fk_name = "user"
    extra = 0
    can_delete = False
    fields = ("old_username", "new_username", "reason", "changed_at", "changed_by")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [ProfileInline, UsernameHistoryInline]


@admin.register(UsernameHistory)
class UsernameHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "old_username",
        "new_username",
        "reason",
        "changed_at",
        "changed_by",
    )
    list_filter = ("reason", "changed_at")
    search_fields = (
        "user__username",
        "user__email",
        "old_username",
        "new_username",
    )
    readonly_fields = (
        "user",
        "old_username",
        "new_username",
        "reason",
        "changed_at",
        "changed_by",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "location",
        "email_notifications",
        "sms_notifications",
    )
    list_filter = ("role", "email_notifications", "sms_notifications")
    search_fields = ("user__username", "user__email", "phone", "location")
