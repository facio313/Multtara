"""Session authentication bound to the current portfolio edge identity."""

from django.conf import settings
from django.contrib.auth import logout
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .sso import request_matches_sso_user


class PortfolioSessionAuthentication(SessionAuthentication):
    """Reject a native session when its trusted SSO subject is no longer current."""

    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        if not user or not user.is_active:
            return None

        if settings.PONGDANG_SSO_ENABLED and not request_matches_sso_user(
            request, user
        ):
            # Flush the stale native session so re-entering through SSO can
            # establish the newly asserted identity instead of looping.
            logout(request._request)
            raise AuthenticationFailed(
                "The portfolio SSO session could not be validated."
            )

        self.enforce_csrf(request)
        return user, None
