from __future__ import annotations

from django.conf import settings
from django.contrib.auth import login, logout, update_session_auth_hash
from django.db.models.deletion import ProtectedError
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trips.throttles import (
    AccountMutationUserRateThrottle,
    AuthenticationAnonRateThrottle,
    SensitiveAccountUserRateThrottle,
    UserMutationRateThrottle,
)

from .models import EcoAction, Passport, UserActivity
from .permissions import IsPortfolioUser
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
from .sso import (
    SsoIdentityConflict,
    bind_sso_session,
    resolve_sso_user,
    trusted_sso_identity,
)


def _serialized_user(user, identity=None):
    data = dict(UserSelfSerializer(user).data)
    if identity is not None:
        data["role"] = identity.role
        data["groups"] = list(identity.groups)
    return data


def _sso_managed_response():
    return Response(
        {"detail": "This credential is managed by portfolio single sign-on."},
        status=status.HTTP_403_FORBIDDEN,
    )


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
    permission_classes = (IsPortfolioUser,)

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
        identity = trusted_sso_identity(request)
        if identity is None:
            return Response(
                {"detail": "A validated proxy identity is required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            user = resolve_sso_user(identity)
        except SsoIdentityConflict:
            # Do not retain a previous native session after an ambiguous or
            # contradictory identity assertion.
            logout(request._request)
            return Response(
                {"detail": "The portfolio identity conflicts with an account."},
                status=status.HTTP_409_CONFLICT,
            )
        if not user.is_active:
            return Response(
                {"detail": "This account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        login(request, user)
        bind_sso_session(request, identity)
        return Response(_serialized_user(user, identity))


@method_decorator(csrf_protect, name="dispatch")
class CurrentUserView(APIView):
    permission_classes = (IsPortfolioUser,)

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
        return Response(
            _serialized_user(
                request.user,
                getattr(request, "portfolio_sso_identity", None),
            )
        )

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
    permission_classes = (IsPortfolioUser,)
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
    permission_classes = (IsPortfolioUser,)
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
    permission_classes = (IsPortfolioUser,)
    serializer_class = PassportSerializer

    def get_queryset(self):
        return (
            Passport.objects.filter(user=self.request.user)
            .select_related("spot")
            .order_by("-verified_at", "-id")
        )


class EcoActionListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsPortfolioUser,)
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
