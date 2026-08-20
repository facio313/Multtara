from django.urls import path

from .views import (
    CsrfTokenView,
    CurrentUserView,
    EcoActionListCreateView,
    LoginView,
    LogoutView,
    PassportListView,
    PasswordChangeView,
    RegistrationView,
    SsoLoginView,
    UserActivityListCreateView,
)


urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="csrf"),
    path("register/", RegistrationView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("sso/", SsoLoginView.as_view(), name="sso"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("password/", PasswordChangeView.as_view(), name="password"),
    path("activities/", UserActivityListCreateView.as_view(), name="activities"),
    path("passports/", PassportListView.as_view(), name="passports"),
    path("eco-actions/", EcoActionListCreateView.as_view(), name="eco-actions"),
]
