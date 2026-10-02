"""Query parameters are validated strictly: unknown, blank or repeated ones are a 400, never ignored.

A typo such as ``?stauts=delivered`` used to return the whole unfiltered list with a 200, which looks like
an answer but is not the one asked for. Found by Schemathesis (docs/testing.md).
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.requests_desk.services import submit_request

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator(api_as):
    return api_as("operator")


@pytest.fixture
def admin(api_as):
    return api_as("admin")


def details(response):
    assert response.status_code == 400, response.content
    error = response.json()["error"]
    assert error["code"] == "invalid"
    return error["details"]


@pytest.mark.parametrize(
    ("url", "who"),
    [
        ("/api/requests/", "operator"),
        ("/api/episodes/", "operator"),
        ("/api/imports/", "operator"),
        ("/api/users/", "admin"),
        ("/api/notifications/", "operator"),
        ("/api/analytics/", "operator"),
    ],
)
def test_an_unknown_parameter_is_refused(request, url, who):
    client = request.getfixturevalue(who)

    assert details(client.get(url, {"stauts": "delivered"})) == {"stauts": ["Unknown query parameter."]}


def test_a_blank_filter_is_refused(operator):
    assert details(operator.get("/api/requests/", {"status": ""})) == {
        "status": ["This field may not be blank."]
    }


def test_a_repeated_filter_is_refused(operator):
    response = operator.get("/api/requests/?status=submitted&status=delivered")

    assert details(response) == {"status": ["Give this parameter only once."]}


def test_pagination_parameters_are_allowed_on_lists(operator):
    assert operator.get("/api/requests/", {"page": 1, "page_size": 10}).status_code == 200


def test_pagination_parameters_are_refused_where_nothing_is_paginated(operator):
    assert details(operator.get("/api/analytics/", {"page": 2})) == {"page": ["Unknown query parameter."]}


@pytest.mark.parametrize("value", ["null", "yes", "1"])
def test_boolean_filters_take_only_true_or_false(operator, value):
    assert "unread" in details(operator.get("/api/notifications/", {"unread": value}))


def test_the_unread_filter_still_works(operator):
    response = operator.get("/api/notifications/", {"unread": "true"})

    assert response.status_code == 200


def test_the_assignment_history_flag_is_validated(operator, make_user):
    client = make_user(email="client@example.com")
    deadline = timezone.localdate() + timedelta(days=9)
    request = submit_request(client, task_name="pick cup", episodes_requested=1, deadline=deadline)
    url = f"/api/requests/{request.id}/assignments/"

    assert operator.get(url, {"history": "true"}).status_code == 200
    assert "history" in details(operator.get(url, {"history": "null"}))
