"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts import views as accounts_views
from analytics import views as analytics_views
from chat import views as chat_views
from notifications import views as notifications_views

urlpatterns = [
    path(
        '',
        RedirectView.as_view(pattern_name='listings', permanent=False),
        name='home',
    ),
    path('admin/', admin.site.urls),
    path('accounts/', accounts_views.profile_view, name='profile'),
    path(
        'accounts/username/',
        accounts_views.username_change,
        name='username_change',
    ),
    # Roles must be chosen before allauth starts a social OAuth handshake.
    path(
        'accounts/social/<str:provider>/start/<str:role>/',
        accounts_views.social_signup_start,
        name='social_signup_start',
    ),
    # allauth owns login, signup, verification, password reset, and social login.
    path('accounts/', include('allauth.urls')),
    path('analytics/', analytics_views.analytics_view, name='analytics'),
    path('chat/', chat_views.chat_view, name='chat'),
    path('listings/', include('listings.urls')),
    path('notifications/', notifications_views.notifications_view, name='notifications'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) + static(
    settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
)