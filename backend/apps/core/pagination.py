from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """25 per page by default; clients may ask for more, but never more than 100 (bounded query cost)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
