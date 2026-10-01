"""OpenAPI: every operation documents the errors it can return, in the one error shape (apps.core.exceptions).

The common errors are derived from the operation itself, so new endpoints get them without annotations:

- 400 when it takes a body or query filters; 404 when its path has an id or it is paginated
  (a page past the end);
- 401 and 403 when it needs a signed-in user; 429 everywhere (every endpoint is rate limited).

Errors that depend on the business rules (409 conflicts, the public auth endpoints' 401 and 403) are
declared on the view with ``error_response``.
"""

from drf_spectacular.openapi import AutoSchema as SpectacularAutoSchema
from drf_spectacular.utils import OpenApiResponse
from rest_framework import serializers


class ErrorBodySerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Stable, machine-readable error code, e.g. `invalid_transition`.")
    message = serializers.CharField(help_text="Readable explanation, safe to show to the user.")
    details = serializers.JSONField(
        required=False, help_text="Extra context; for 400 errors, the problems per field."
    )


class ErrorSerializer(serializers.Serializer):
    error = ErrorBodySerializer()


def error_response(description: str) -> OpenApiResponse:
    return OpenApiResponse(ErrorSerializer, description=description)


PAGE_PARAMETERS = {"page", "page_size"}


class AutoSchema(SpectacularAutoSchema):
    def get_operation(self, path, path_regex, path_prefix, method, registry):
        operation = super().get_operation(path, path_regex, path_prefix, method, registry)
        if operation is None:
            return None
        error = {"content": {"application/json": {"schema": self._error_schema()}}}
        responses = operation.setdefault("responses", {})
        for code, description in self._common_errors(operation, path):
            responses.setdefault(code, {"description": description, **error})
        return dict(operation, responses=dict(sorted(responses.items())))

    def _error_schema(self):
        return self.resolve_serializer(ErrorSerializer, "response").ref

    def _common_errors(self, operation, path):
        query = {p["name"] for p in operation.get("parameters", []) if p["in"] == "query"}
        signed_in = {} not in operation.get("security", [{}])

        if "requestBody" in operation or query - PAGE_PARAMETERS:
            yield "400", "Invalid input; `details` lists the problems per field."
        if signed_in:
            yield "401", "Not signed in, or the access token is invalid or expired."
            yield "403", "Signed in, but your role may not do this."
        if "{" in path or query & PAGE_PARAMETERS:
            yield "404", "Not found, or not visible to you (or a page past the end)."
        yield "429", "Too many requests; retry after the number of seconds in `Retry-After`."
