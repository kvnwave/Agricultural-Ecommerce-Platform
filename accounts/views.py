from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProfileForm


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
