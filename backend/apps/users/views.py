from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trips.throttles import (
    AccountMutationUserRateThrottle,
    AuthenticationAnonRateThrottle,
    SensitiveAccountUserRateThrottle,
    UserMutationRateThrottle,
)

from .models import EcoAction, Passport, UserActivity
from .serializers import (
    AccountDeleteSerializer,
    EcoActionSerializer,
    LoginSerializer,
    PassportSerializer,
    PasswordChangeSerializer,
    RegistrationSerializer,
    UserActivitySerializer,
    UserSelfSerializer,
)

User = get_user_model()


def _sso_managed_response():
    return Response(
        {"detail": "This credential is managed by portfolio single sign-on."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _trusted_sso_identity(request):
    username = request.META.get("HTTP_REMOTE_USER", "").strip()
    email = request.META.get("HTTP_REMOTE_EMAIL", "").strip().lower()
    display_name = request.META.get("HTTP_REMOTE_NAME", "").strip()
    if not username or not email:
        return None
    if any(
        len(value) > 254
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        for value in (username, email, display_name)
    ):
        return None
    if len(username) > User._meta.get_field("username").max_length:
        return None
    try:
        UnicodeUsernameValidator()(username)
        validate_email(email)
    except ValidationError:
        return None
    return username, email, display_name


def _get_or_create_sso_user(username, email, display_name):
    user = User.objects.filter(username__iexact=username).first()
    if user is None:
        user = User.objects.filter(email__iexact=email).first()
    if user is not None:
        return user
    try:
        with transaction.atomic():
            user = User(username=username, email=email)
            if display_name:
                user.first_name = display_name[:150]
            user.set_unusable_password()
            user.save()
            return user
    except IntegrityError:
        return User.objects.get(username__iexact=username)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        # Returning the token supports non-browser API clients while the cookie
        # is the normal same-origin SPA path. It contains no account secret.
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class RegistrationView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AuthenticationAnonRateThrottle,)

    def post(self, request):
        if settings.PONGDANG_SSO_ENABLED:
            return _sso_managed_response()
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(UserSelfSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AuthenticationAnonRateThrottle,)

    def post(self, request):
        if settings.PONGDANG_SSO_ENABLED:
            return _sso_managed_response()
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        login(request, serializer.validated_data["user"])
        return Response(UserSelfSerializer(serializer.validated_data["user"]).data)


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class SsoLoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        if not settings.PONGDANG_SSO_ENABLED:
            return Response(status=status.HTTP_404_NOT_FOUND)
        identity = _trusted_sso_identity(request)
        if identity is None:
            return Response(
                {"detail": "A validated proxy identity is required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user = _get_or_create_sso_user(*identity)
        if not user.is_active:
            return Response(
                {"detail": "This account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        login(request, user)
        return Response(UserSelfSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class CurrentUserView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_throttles(self):
        if self.request.method in {"PATCH", "DELETE"}:
            throttle = (
                SensitiveAccountUserRateThrottle
                if self.request.method == "DELETE"
                else AccountMutationUserRateThrottle
            )
            return [throttle()]
        return super().get_throttles()

    def get(self, request):
        return Response(UserSelfSerializer(request.user).data)

    def patch(self, request):
        data = request.data
        if settings.PONGDANG_SSO_ENABLED and "email" in request.data:
            data = request.data.copy()
            data.pop("email", None)
        serializer = UserSelfSerializer(
            request.user,
            data=data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        if settings.PONGDANG_SSO_ENABLED:
            return _sso_managed_response()
        serializer = AccountDeleteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        try:
            user.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "This account owns retained verification audit records "
                        "and must be deactivated through the operator workflow."
                    ),
                    "code": "ACCOUNT_RETENTION_REVIEW_REQUIRED",
                },
                status=status.HTTP_409_CONFLICT,
            )
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class PasswordChangeView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (SensitiveAccountUserRateThrottle,)

    def post(self, request):
        if settings.PONGDANG_SSO_ENABLED:
            return _sso_managed_response()
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=("password",))
        update_session_auth_hash(request, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserActivityListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserActivitySerializer
    throttle_classes = (UserMutationRateThrottle,)

    def get_queryset(self):
        return (
            UserActivity.objects.filter(user=self.request.user)
            .select_related("spot")
            .order_by("-created_at", "-id")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PassportListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PassportSerializer

    def get_queryset(self):
        return (
            Passport.objects.filter(user=self.request.user)
            .select_related("spot")
            .order_by("-verified_at", "-id")
        )


class EcoActionListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = EcoActionSerializer
    throttle_classes = (UserMutationRateThrottle,)

    def get_queryset(self):
        return (
            EcoAction.objects.filter(user=self.request.user)
            .select_related("spot", "verified_by")
            .order_by("-submitted_at", "-id")
        )

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user, state=EcoAction.VerificationState.PENDING
        )
