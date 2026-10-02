"""The OpenAPI document lists the errors each operation can return, all in the one error shape.

Client code (and the generated frontend types) can then handle a 409 or a 429 from the contract alone,
without reading the backend.
"""

import pytest
from drf_spectacular.generators import SchemaGenerator

ERROR_REF = "#/components/schemas/Error"


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.fixture(scope="module")
def operations(schema):
    return {
        operation["operationId"]: operation
        for path in schema["paths"].values()
        for operation in path.values()
    }


def error_codes(operation):
    return {code for code in operation["responses"] if code.startswith("4")}


def test_the_error_shape_is_one_shared_component(schema):
    error = schema["components"]["schemas"]["Error"]
    body = schema["components"]["schemas"]["ErrorBody"]

    assert error["required"] == ["error"]
    assert set(body["required"]) == {"code", "message"}
    assert "details" in body["properties"]


def test_every_error_response_uses_the_shared_shape(operations):
    for operation_id, operation in operations.items():
        for code in error_codes(operation):
            content = operation["responses"][code]["content"]["application/json"]
            assert content["schema"] == {"$ref": ERROR_REF}, (operation_id, code)


def test_every_operation_can_be_rate_limited(operations):
    assert all("429" in operation["responses"] for operation in operations.values())


@pytest.mark.parametrize(
    ("operation_id", "expected"),
    [
        # Signed-in endpoints: 401 without a valid token, 403 for the wrong role.
        ("requests_list", {"400", "401", "403", "404", "429"}),  # bad filters (400), past the last page (404)
        ("requests_retrieve", {"401", "403", "404", "429"}),
        ("imports_list", {"400", "401", "403", "404", "429"}),  # 400: unknown or malformed query parameters
        ("requests_create", {"400", "401", "403", "409", "422", "429"}),  # 409/422: Idempotency-Key
        # Workflow and assignment conflicts.
        ("requests_transitions_create", {"400", "401", "403", "404", "409", "422", "429"}),
        ("requests_assignments_create", {"400", "401", "403", "404", "409", "422", "429"}),
        ("requests_assignments_destroy", {"401", "403", "404", "409", "429"}),
        ("users_partial_update", {"400", "401", "403", "404", "409", "429"}),
        # Public auth endpoints: wrong credentials or no session are 401; cross-site requests are 403.
        ("auth_login_create", {"400", "401", "403", "429"}),
        ("auth_refresh_create", {"401", "403", "429"}),
        ("auth_logout_create", {"403", "429"}),
    ],
)
def test_each_operation_lists_the_errors_it_can_return(operations, operation_id, expected):
    assert error_codes(operations[operation_id]) == expected
