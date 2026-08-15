import re

from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.response import Response

from .lockout import clear_failures, client_ip, is_locked, register_failure
from .models import User

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._]{2,29}$")
GENERIC_LOGIN = "아이디 또는 비밀번호가 올바르지 않습니다."
LOCKED = "잠시 후 다시 시도해 주세요."
_DUMMY_HASH = make_password("not-a-real-password")


def _public_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "home_region": user.home_region,
        "persona_type": user.persona_type,
        "date_joined": user.date_joined,
    }


class AuthThrottle(ScopedRateThrottle):
    scope = "auth"


class RegisterThrottle(ScopedRateThrottle):
    scope = "auth_register"


class UsernameField(serializers.CharField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data).strip()
        if not USERNAME_RE.match(value):
            raise serializers.ValidationError(
                "아이디는 영문으로 시작해 3~30자의 영문, 숫자, 점, 밑줄만 사용할 수 있습니다."
            )
        return value


class RegisterSerializer(serializers.Serializer):
    username = UsernameField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    home_region = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "비밀번호가 일치하지 않습니다."})
        if User.objects.filter(username__iexact=attrs["username"]).exists():
            raise serializers.ValidationError({"username": "이미 사용 중인 아이디입니다."})
        user = User(username=attrs["username"])
        try:
            validate_password(attrs["password"], user=user)
        except ValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated):
        user = User(username=validated["username"], home_region=validated.get("home_region") or "")
        user.set_password(validated["password"])
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        attrs["username"] = attrs["username"].strip()
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "비밀번호가 일치하지 않습니다."})
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "현재 비밀번호가 올바르지 않습니다."})
        try:
            validate_password(attrs["new_password"], user=user)
        except ValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)}) from exc
        return attrs


def _authenticate(username: str, password: str) -> User | None:
    user = User.objects.filter(username__iexact=username).first()
    if user is None:
        check_password(password, _DUMMY_HASH)
        return None
    if not user.check_password(password) or not user.is_active:
        return None
    return user


class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthThrottle]

    @method_decorator(never_cache)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        clear_failures(user.username, client_ip(request))
        return Response(_public_user(user), status=201)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        ip = client_ip(request)
        if is_locked(username, ip):
            return Response({"detail": LOCKED}, status=429)
        user = _authenticate(username, serializer.validated_data["password"])
        if user is None:
            register_failure(username, ip)
            return Response({"detail": GENERIC_LOGIN}, status=400)
        login(request, user)
        clear_failures(username, ip)
        return Response(_public_user(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(never_cache)
    def get(self, request):
        return Response(_public_user(request.user))


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthThrottle]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        return Response(_public_user(request.user))
