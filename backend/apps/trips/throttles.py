"""Anonymous request throttles keyed only by the trusted connection peer."""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class RemoteAddressAnonRateThrottle(AnonRateThrottle):
    """Ignore caller-controlled forwarding headers when identifying a client."""

    def get_ident(self, request) -> str:
        return str(request.META.get("REMOTE_ADDR") or "unknown-peer")


class RecommendationAnonRateThrottle(RemoteAddressAnonRateThrottle):
    """A stricter anonymous budget for recommendation computation."""

    scope = "recommendations"


class AuthenticationAnonRateThrottle(RemoteAddressAnonRateThrottle):
    """A small peer-keyed budget for credential verification endpoints."""

    scope = "authentication"


class RecommendationUserRateThrottle(UserRateThrottle):
    """Bound expensive ranking/itinerary work for authenticated sessions too."""

    rate = "60/hour"


class UserMutationRateThrottle(UserRateThrottle):
    """Bound first-party activity rows without trusting forwarded addresses."""

    rate = "120/hour"


class AccountMutationUserRateThrottle(UserRateThrottle):
    """Bound authenticated profile and saved-plan mutations."""

    rate = "60/hour"


class SensitiveAccountUserRateThrottle(UserRateThrottle):
    """Strict budget for password checks and account deletion attempts."""

    rate = "10/hour"
