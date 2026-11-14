from allauth.socialaccount.providers import registry
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

from .forms import ProfileForm, SOCIAL_SIGNUP_ROLE_SESSION_KEY
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

    return render(request, "accounts/accounts.html", {"form": form})


@require_GET
def social_signup_start(request, provider, role):
    """Remember the chosen role before allauth sends the user to a provider."""

    if role not in Profile.Role.values:
        raise Http404("Unknown account type.")

    provider_ids = {provider_class.id for provider_class in registry.get_class_list()}
    if provider not in provider_ids:
        raise Http404("Unknown social provider.")

    try:
        login_url = reverse(f"{provider}_login")
    except NoReverseMatch:
        raise Http404("Social provider login is unavailable.")

    request.session[SOCIAL_SIGNUP_ROLE_SESSION_KEY] = role
    return redirect(login_url)
