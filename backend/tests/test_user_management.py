import logging

import pytest
from django.contrib.auth import get_user_model

from tests.test_auth_login import ME, bearer, login

USERS = "/api/users/"
User = get_user_model()

pytestmark = pytest.mark.django_db

STRONG_PASSWORD = "violet tractor under the bridge"


def user_url(user):
    return f"{USERS}{user.id}/"


@pytest.fixture
def admin(api_as):
    return api_as("admin", email="ada@example.com", full_name="Ada Admin")


def new_user(**overrides):
    data = {
        "email": "new.client@example.com",
        "full_name": "New Client",
        "role": "client",
        "organisation": "Gamma Robotics",
        "password": STRONG_PASSWORD,
    }
    data.update(overrides)
    return data


class TestOnlyAdmins:
    @pytest.mark.parametrize("role", ["client", "operator"])
    def test_other_roles_cannot_list_create_or_change_users(self, api_as, make_user, role):
        client = api_as(role)
        target = make_user(email="target@example.com")

        assert client.get(USERS).status_code == 403
        assert client.post(USERS, new_user(), format="json").status_code == 403
        assert client.patch(user_url(target), {"role": "admin"}, format="json").status_code == 403

    def test_users_are_never_deleted(self, admin, make_user):
        # Deactivate instead: requests and audit events keep pointing at the user.
        assert admin.delete(user_url(make_user(email="t@example.com"))).status_code == 405


class TestCreating:
    def test_creates_a_user_with_a_hashed_password(self, admin):
        response = admin.post(USERS, new_user(), format="json")

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new.client@example.com"
        assert body["is_active"] is True
        assert "password" not in body
        user = User.objects.get(email="new.client@example.com")
        assert user.check_password(STRONG_PASSWORD)
        assert user.password != STRONG_PASSWORD

    def test_the_new_user_can_log_in(self, admin, api_client):
        admin.post(USERS, new_user(email="Mixed.Case@Example.com"), format="json")

        assert login(api_client, "mixed.case@example.com", STRONG_PASSWORD).status_code == 200

    def test_email_must_be_unique_ignoring_case(self, admin, make_user):
        make_user(email="taken@example.com")

        response = admin.post(USERS, new_user(email="TAKEN@example.com"), format="json")

        assert response.status_code == 400
        assert "email" in response.json()["error"]["details"]

    @pytest.mark.parametrize("password", ["short", "123456789012", "password1234"])
    def test_weak_passwords_are_rejected(self, admin, password):
        response = admin.post(USERS, new_user(password=password), format="json")

        assert response.status_code == 400
        assert "password" in response.json()["error"]["details"]

    def test_role_must_be_known(self, admin):
        response = admin.post(USERS, new_user(role="superhero"), format="json")

        assert response.status_code == 400
        assert "role" in response.json()["error"]["details"]


class TestListing:
    def test_lists_and_filters_users(self, admin, make_user):
        make_user(email="ops1@example.com", role="operator")
        make_user(email="gone@example.com", role="client", is_active=False)

        everyone = [u["email"] for u in admin.get(USERS).json()["results"]]
        operators = [u["email"] for u in admin.get(USERS, {"role": "operator"}).json()["results"]]
        inactive = [u["email"] for u in admin.get(USERS, {"is_active": "false"}).json()["results"]]
        found = [u["email"] for u in admin.get(USERS, {"search": "OPS1"}).json()["results"]]

        assert everyone == ["ada@example.com", "gone@example.com", "ops1@example.com"]
        assert operators == ["ops1@example.com"]
        assert inactive == ["gone@example.com"]
        assert found == ["ops1@example.com"]


class TestChangingAccess:
    def test_changing_a_role_ends_the_users_sessions(self, admin, api_client, make_user):
        target = make_user(email="target@example.com", role="client")
        bearer(api_client, login(api_client, "target@example.com").json()["access"])

        response = admin.patch(user_url(target), {"role": "operator"}, format="json")

        assert response.status_code == 200
        assert response.json()["role"] == "operator"
        assert api_client.get(ME).status_code == 401  # their old token no longer works

    def test_deactivating_ends_sessions_and_blocks_login(self, admin, api_client, make_user):
        target = make_user(email="target@example.com")
        bearer(api_client, login(api_client, "target@example.com").json()["access"])

        admin.patch(user_url(target), {"is_active": False}, format="json")

        assert api_client.get(ME).status_code == 401
        assert login(api_client, "target@example.com").status_code == 401

    def test_resetting_a_password_ends_sessions_and_applies_the_policy(self, admin, api_client, make_user):
        target = make_user(email="target@example.com")
        bearer(api_client, login(api_client, "target@example.com").json()["access"])

        assert admin.patch(user_url(target), {"password": "short"}, format="json").status_code == 400
        assert admin.patch(user_url(target), {"password": STRONG_PASSWORD}, format="json").status_code == 200

        assert api_client.get(ME).status_code == 401
        assert login(api_client, "target@example.com", STRONG_PASSWORD).status_code == 200

    def test_editing_a_name_does_not_end_sessions(self, admin, api_client, make_user):
        target = make_user(email="target@example.com")
        bearer(api_client, login(api_client, "target@example.com").json()["access"])

        admin.patch(user_url(target), {"full_name": "Renamed", "organisation": "New Org"}, format="json")

        assert api_client.get(ME).status_code == 200

    def test_email_cannot_be_changed(self, admin, make_user):
        target = make_user(email="target@example.com")

        admin.patch(user_url(target), {"email": "other@example.com"}, format="json")

        target.refresh_from_db()
        assert target.email == "target@example.com"


class TestAdminsCannotLockThemselvesOut:
    @pytest.mark.parametrize("change", [{"role": "operator"}, {"is_active": False}])
    def test_an_admin_cannot_demote_or_deactivate_themselves(self, admin, change):
        response = admin.patch(user_url(admin.user), change, format="json")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "cannot_change_own_access"

    def test_another_admin_can_be_demoted_while_one_remains(self, admin, make_user):
        other = make_user(email="other.admin@example.com", role="admin")

        assert admin.patch(user_url(other), {"role": "operator"}, format="json").status_code == 200

    def test_the_last_active_admin_cannot_be_removed(self, make_user):
        from apps.accounts.services import LastActiveAdmin, update_user

        only_admin = make_user(email="only@example.com", role="admin")
        # Through the service directly: over the API the "own access" rule already covers this case.
        with pytest.raises(LastActiveAdmin):
            update_user(
                only_admin,
                actor=make_user(email="system@example.com", role="admin", is_active=False),
                role="operator",
            )


def test_changes_are_recorded_in_the_security_log(admin, make_user, caplog):
    caplog.set_level(logging.INFO, logger="desk.security")
    target = make_user(email="target@example.com")

    admin.patch(user_url(target), {"role": "operator", "full_name": "T"}, format="json")

    [record] = [r for r in caplog.records if getattr(r, "event", "") == "admin.user_updated"]
    assert record.target_user_id == str(target.id)
    assert record.user_id == str(admin.user.id)
    assert sorted(record.changed_fields) == ["full_name", "role"]
