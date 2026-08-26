from django.conf import settings
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .sso import PORTFOLIO_ROLE_RANK


def portfolio_role_for_request(request) -> str | None:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    if settings.PONGDANG_SSO_ENABLED:
        identity = getattr(request, "portfolio_sso_identity", None)
        return identity.role if identity is not None else None
    if user.is_superuser:
        return "chief-admin"
    if user.is_staff:
        return "admin"
    return "user"


class HasPortfolioRole(BasePermission):
    required_role = "user"

    def has_permission(self, request, view):
        role = portfolio_role_for_request(request)
        return bool(
            role in PORTFOLIO_ROLE_RANK
            and PORTFOLIO_ROLE_RANK[role] >= PORTFOLIO_ROLE_RANK[self.required_role]
        )


class IsPortfolioUser(HasPortfolioRole):
    required_role = "user"


class IsPortfolioAdmin(HasPortfolioRole):
    required_role = "admin"


class IsPortfolioChiefAdmin(HasPortfolioRole):
    required_role = "chief-admin"


class IsPortfolioUserOrReadOnly(IsPortfolioUser):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or super().has_permission(request, view)
