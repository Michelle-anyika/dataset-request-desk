"""Managing accounts (docs/security.md §4). Views call these; they never change users directly."""

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import exceptions, status

from apps.accounts.models import Role
from apps.accounts.sessions import revoke_all_sessions

# Changing any of these means the user's existing sessions must not carry on with the old access.
ACCESS_FIELDS = {"role", "is_active", "password"}


class CannotChangeOwnAccess(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "cannot_change_own_access"
    default_detail = "You can't demote or deactivate your own account; ask another admin."


class LastActiveAdmin(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "last_active_admin"
    default_detail = "This is the last active admin; make someone else an admin first."


def create_user(*, email, password, full_name, role, organisation=""):
    return get_user_model().objects.create_user(
        email=email, password=password, full_name=full_name, role=role, organisation=organisation
    )


@transaction.atomic
def update_user(user, *, actor, **changes) -> list[str]:
    """Apply ``changes`` to ``user`` and return the names of the fields that actually changed.

    A role change, deactivation or password reset ends every session of the user at once.
    """
    User = get_user_model()
    user = User.objects.select_for_update().get(pk=user.pk)

    removes_admin = (
        user.role == Role.ADMIN
        and user.is_active
        and (changes.get("role", Role.ADMIN) != Role.ADMIN or changes.get("is_active", True) is False)
    )
    if removes_admin:
        if user.pk == actor.pk:
            raise CannotChangeOwnAccess()
        # Lock every admin row: two admins demoting each other at the same moment can't both succeed.
        admins = User.objects.select_for_update().filter(role=Role.ADMIN, is_active=True).exclude(pk=user.pk)
        if not list(admins):
            raise LastActiveAdmin()

    changed = []
    password = changes.pop("password", None)
    if password is not None:
        user.set_password(password)
        changed.append("password")
    for field, value in changes.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed.append(field)
    if changed:
        user.save()
    if ACCESS_FIELDS & set(changed):
        revoke_all_sessions(user)
    return changed
