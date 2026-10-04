from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """25 per page by default; clients may ask for more, but never more than 100 (bounded query cost)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_schema_operation_parameters(self, view):
        # Document the bounds that apps.core.query enforces, so clients (and the fuzzer) know them.
        parameters = super().get_schema_operation_parameters(view)
        bounds = {"page": {"minimum": 1}, "page_size": {"minimum": 1, "maximum": self.max_page_size}}
        for parameter in parameters:
            parameter["schema"].update(bounds.get(parameter["name"], {}))
        return parameters
