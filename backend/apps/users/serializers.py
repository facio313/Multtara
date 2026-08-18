from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from services.public_urls import public_https_url

from .models import EcoAction, Passport, UserActivity


User = get_user_model()

PERSONA_CHOICES = ("active", "family", "wellness", "local", "stay", "")


class UserSelfSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "persona_type",
            "mood_state",
            "home_region",
            "preferred_locale",
            "date_joined",
        )
        read_only_fields = ("id", "username", "date_joined")

    def validate_persona_type(self, value: str) -> str:
        value = value.strip().lower()
        if value not in PERSONA_CHOICES:
            raise serializers.ValidationError("Unsupported persona type.")
        return value

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_mood_state(self, value: str) -> str:
        return value.strip()

    def validate_home_region(self, value: str) -> str:
        return value.strip()


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ("username", "password", "email", "preferred_locale")

    def validate_username(self, value: str) -> str:
        value = value.strip()
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("An account with this username exists.")
        return value

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        candidate = User(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
        )
        validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["username"].strip(),
            password=attrs["password"],
        )
        if user is None or not user.is_active:
            raise serializers.ValidationError(
                "Unable to sign in with the supplied credentials."
            )
        attrs["user"] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        validate_password(value, user=self.context["request"].user)
        return value


class AccountDeleteSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value


class SpotReferenceSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)
    region = serializers.CharField(read_only=True)


class UserActivitySerializer(serializers.ModelSerializer):
    spot_detail = SpotReferenceSerializer(source="spot", read_only=True)

    class Meta:
        model = UserActivity
        fields = (
            "id",
            "spot",
            "spot_detail",
            "action",
            "rating",
            "review_text",
            "created_at",
        )
        read_only_fields = ("id", "spot_detail", "created_at")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        action = attrs.get("action")
        rating = attrs.get("rating")
        review_text = attrs.get("review_text", "").strip()
        if action == UserActivity.Action.REVIEW:
            if rating is None and not review_text:
                raise serializers.ValidationError(
                    "A review requires a rating or review text."
                )
        elif rating is not None or review_text:
            raise serializers.ValidationError(
                "Rating and review text are accepted only for review actions."
            )
        attrs["review_text"] = review_text
        return attrs


class PassportSerializer(serializers.ModelSerializer):
    spot = SpotReferenceSerializer(read_only=True)
    evidence_url = serializers.SerializerMethodField()

    class Meta:
        model = Passport
        fields = (
            "id",
            "spot",
            "verified_at",
            "verification_method",
            "verification_source",
            "evidence_url",
            "badge_earned",
            "eco_action",
        )
        read_only_fields = fields

    def get_evidence_url(self, instance: Passport) -> str:
        return public_https_url(instance.evidence_url)


class EcoActionSerializer(serializers.ModelSerializer):
    spot_detail = SpotReferenceSerializer(source="spot", read_only=True)
    verified_by = serializers.SerializerMethodField()

    class Meta:
        model = EcoAction
        fields = (
            "id",
            "spot",
            "spot_detail",
            "action_type",
            "note",
            "evidence_url",
            "occurred_on",
            "state",
            "submitted_at",
            "verified_at",
            "verified_by",
        )
        read_only_fields = (
            "id",
            "spot_detail",
            "state",
            "submitted_at",
            "verified_at",
            "verified_by",
        )

    def validate_note(self, value: str) -> str:
        return value.strip()

    def validate_evidence_url(self, value: str) -> str:
        if not value:
            return ""
        sanitized = public_https_url(value)
        if not sanitized:
            raise serializers.ValidationError(
                "Evidence URL must be a public HTTPS URL."
            )
        return sanitized

    def validate_occurred_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Eco action date cannot be in the future.")
        return value

    def get_verified_by(self, instance: EcoAction) -> str | None:
        if instance.verified_by_id is None:
            return None
        # Staff usernames are account identifiers and need not be disclosed to
        # the submitter. The immutable verification state/timestamp convey the
        # public fact without exposing an operator login name.
        return "operator"

    def to_representation(self, instance: EcoAction) -> dict:
        representation = super().to_representation(instance)
        # Legacy/imported rows remain untrusted even though current writes are
        # normalized by both the serializer and the model.
        representation["evidence_url"] = public_https_url(instance.evidence_url)
        return representation
