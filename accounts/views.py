from allauth.socialaccount.providers import registry
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET, require_http_methods

from . import usernames
from .forms import ProfileForm, SOCIAL_SIGNUP_ROLE_SESSION_KEY, UsernameChangeForm
from .models import Profile


@login_required
def profile_view(request):
    profile = request.user.profile

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile photo was updated.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile)

    cooldown_ends = None
    if not request.user.is_staff:
        cooldown_ends = usernames.username_cooldown_ends(request.user)

    return render(
        request,
        "accounts/accounts.html",
        {"form": form, "cooldown_ends": cooldown_ends},
    )


@login_required
@require_http_methods(["GET", "POST"])
def username_change(request):
    cooldown_ends = None
    if not request.user.is_staff:
        cooldown_ends = usernames.username_cooldown_ends(request.user)

    if request.method == "POST" and cooldown_ends is None:
        form = UsernameChangeForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                usernames.change_username(
                    request.user,
                    form.cleaned_data["username"],
                    actor=request.user,
                )
            except usernames.UsernameCooldownError as exc:
                cooldown_ends = exc.available_at
                form.add_error(
                    None,
                    "You can change your username again on "
                    f"{exc.available_at:%b %d, %Y}.",
                )
            except usernames.UsernameTakenError:
                form.add_error("username", "That username is already taken.")
            except usernames.UsernameUnchangedError:
                form.add_error("username", "That is already your username.")
            else:
                messages.success(request, "Your username was updated.")
                return redirect("profile")
    else:
        form = UsernameChangeForm(user=request.user)

    return render(
        request,
        "accounts/username_change.html",
        {"form": form, "cooldown_ends": cooldown_ends},
    )


@require_GET
def social_signup_start(request, provider, role):
    """Remember the chosen role before allauth sends the user to a provider."""

    if role not in Profile.Role.values:
        raise Http404("Unknown account type.")

    provider_ids = {provider_class.id for provider_class in registry.get_class_list()}
    if provider not in provider_ids:
        raise Http404("Unknown social provider.")
    # Installed but without credentials: the redirect would land on a provider
    # login that cannot start, so treat it as unavailable instead.
    if provider not in settings.SOCIALACCOUNT_PROVIDERS:
        raise Http404("Social provider is not configured.")

    try:
        login_url = reverse(f"{provider}_login")
    except NoReverseMatch:
        raise Http404("Social provider login is unavailable.")

    request.session[SOCIAL_SIGNUP_ROLE_SESSION_KEY] = role
    return redirect(login_url)
