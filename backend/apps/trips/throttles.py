"""Anonymous request throttles keyed only by the trusted connection peer."""

from rest_framework.throttling import AnonRateThrottle


class RemoteAddressAnonRateThrottle(AnonRateThrottle):
    """Ignore caller-controlled forwarding headers when identifying a client."""

    def get_ident(self, request) -> str:
        return str(request.META.get("REMOTE_ADDR") or "unknown-peer")


class RecommendationAnonRateThrottle(RemoteAddressAnonRateThrottle):
    """A stricter anonymous budget for recommendation computation."""

    scope = "recommendations"
