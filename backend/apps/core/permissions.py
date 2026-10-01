"""Role-based permissions. The role is read from the database-loaded user on every request."""

from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class IsClient(BasePermission):
    def has_permission(self, request, view):
        return request.user.role == Role.CLIENT


class IsOperator(BasePermission):
    """Operators and admins: an admin can do everything an operator can."""

    def has_permission(self, request, view):
        return request.user.role in (Role.OPERATOR, Role.ADMIN)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.role == Role.ADMIN
