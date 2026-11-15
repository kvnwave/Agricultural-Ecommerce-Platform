from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.db import transaction

from . import usernames
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


class UserChangeForm(DjangoUserChangeForm):
    """Apply the marketplace policy when staff edit a username."""

    def clean_username(self):
        value = usernames.validate_username(self.cleaned_data["username"])
        if (
            User.objects.filter(username__iexact=value)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError("That username is already taken.")
        return value


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserChangeForm
    inlines = [ProfileInline, UsernameHistoryInline]

    def save_model(self, request, obj, form, change):
        old_username = None
        if change:
            old_username = User.objects.get(pk=obj.pk).username

        username_changed = (
            change
            and usernames.normalize_username(old_username)
            != usernames.normalize_username(obj.username)
        )

        with transaction.atomic():
            if username_changed:
                locked = usernames.change_username(
                    obj,
                    obj.username,
                    actor=request.user,
                    reason=UsernameHistory.Reason.ADMIN,
                )
                # Keep the admin instance in sync so the save below does not
                # write the pre-change timestamp back over the service update.
                obj.username = locked.username
                obj.username_changed_at = locked.username_changed_at
            super().save_model(request, obj, form, change)


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
