from datetime import timedelta

import pytest
from django.utils import timezone

from apps.requests_desk.models import RequestStatus
from apps.requests_desk.services import submit_request

REQUESTS = "/api/requests/"

pytestmark = pytest.mark.django_db


def submit(client_user, task_name="pick cup", days=30):
    return submit_request(
        client_user,
        task_name=task_name,
        episodes_requested=10,
        deadline=timezone.localdate() + timedelta(days=days),
    )


def ids(response):
    return {item["id"] for item in response.json()["results"]}


@pytest.fixture
def two_clients(api_as):
    acme, beta = api_as("client", organisation="Acme Robotics"), api_as("client", organisation="Beta Labs")
    acme_request, beta_request = submit(acme.user), submit(beta.user)
    return acme, beta, acme_request, beta_request


class TestClientScoping:
    def test_a_client_lists_only_their_own_requests(self, two_clients):
        acme, _, acme_request, _ = two_clients

        response = acme.get(REQUESTS)

        assert response.status_code == 200
        assert ids(response) == {str(acme_request.id)}

    def test_another_clients_request_is_not_found(self, two_clients):
        # 404, not 403: a client must not even learn that the request exists.
        acme, _, _, beta_request = two_clients

        response = acme.get(f"{REQUESTS}{beta_request.id}/")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_a_client_can_read_their_own_request(self, two_clients):
        acme, _, acme_request, _ = two_clients

        response = acme.get(f"{REQUESTS}{acme_request.id}/")

        assert response.status_code == 200
        assert response.json()["id"] == str(acme_request.id)

    def test_a_client_cannot_widen_the_scope_with_a_filter(self, two_clients):
        acme, beta, acme_request, _ = two_clients

        response = acme.get(REQUESTS, {"client": str(beta.user.id)})

        assert ids(response) == {str(acme_request.id)}


@pytest.mark.parametrize("role", ["operator", "admin"])
class TestStaffSeeEverything:
    def test_lists_every_clients_requests(self, api_as, two_clients, role):
        _, _, acme_request, beta_request = two_clients

        response = api_as(role).get(REQUESTS)

        assert ids(response) == {str(acme_request.id), str(beta_request.id)}

    def test_reads_any_request(self, api_as, two_clients, role):
        _, _, _, beta_request = two_clients

        assert api_as(role).get(f"{REQUESTS}{beta_request.id}/").status_code == 200

    def test_filters_by_client(self, api_as, two_clients, role):
        _, beta, _, beta_request = two_clients

        response = api_as(role).get(REQUESTS, {"client": str(beta.user.id)})

        assert ids(response) == {str(beta_request.id)}


class TestFilteringAndOrdering:
    def test_filters_by_status(self, api_as, two_clients):
        _, _, acme_request, beta_request = two_clients
        beta_request.status = RequestStatus.IN_PROGRESS
        beta_request.save()

        response = api_as("operator").get(REQUESTS, {"status": "in_progress"})

        assert ids(response) == {str(beta_request.id)}

    @pytest.mark.parametrize("params", [{"status": "lost"}, {"client": "not-a-uuid"}, {"ordering": "notes"}])
    def test_invalid_filters_are_rejected(self, api_as, params):
        response = api_as("operator").get(REQUESTS, params)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid"

    def test_orders_by_deadline_for_the_operator_queue(self, api_as):
        client = api_as("client")
        late, soon = submit(client.user, days=60), submit(client.user, days=5)

        response = api_as("operator").get(REQUESTS, {"ordering": "deadline"})

        assert [item["id"] for item in response.json()["results"]] == [str(soon.id), str(late.id)]

    def test_newest_first_by_default(self, api_as):
        client = api_as("client")
        older, newer = submit(client.user), submit(client.user)

        response = client.get(REQUESTS)

        assert [item["id"] for item in response.json()["results"]] == [str(newer.id), str(older.id)]


class TestPagination:
    def test_results_are_paginated(self, api_as):
        client = api_as("client")
        for _ in range(30):
            submit(client.user)

        body = client.get(REQUESTS).json()

        assert body["count"] == 30
        assert len(body["results"]) == 25
        assert body["next"] is not None

    def test_page_size_can_be_chosen_but_is_capped_at_100(self, api_as):
        client = api_as("client")
        for _ in range(105):
            submit(client.user)

        assert len(client.get(REQUESTS, {"page_size": 50}).json()["results"]) == 50
        assert len(client.get(REQUESTS, {"page_size": 10_000}).json()["results"]) == 100


def test_listing_uses_a_fixed_number_of_queries(api_as, django_assert_max_num_queries):
    # Guards against N+1 queries: the cost must not grow with the number of requests.
    client = api_as("client")
    for _ in range(20):
        submit(client.user)

    with django_assert_max_num_queries(2):  # one count, one page with clients joined
        client.get(REQUESTS)


def test_listing_requires_authentication(api_client):
    assert api_client.get(REQUESTS).status_code == 401
