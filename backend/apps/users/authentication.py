from rest_framework.authentication import SessionAuthentication


class SessionCsrfAuthentication(SessionAuthentication):
    """Session auth that always checks CSRF, including anonymous POSTs."""

    def authenticate(self, request):
        self.enforce_csrf(request)
        user = getattr(request._request, "user", None)
        if user is None or not user.is_authenticated or not user.is_active:
            return None
        return (user, None)

    def authenticate_header(self, request):
        return "Session"
