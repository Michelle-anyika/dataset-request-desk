from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics import cache, queries
from apps.analytics.serializers import AnalyticsRangeSerializer, AnalyticsSerializer
from apps.core.permissions import IsOperator


class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsOperator]

    @extend_schema(parameters=[AnalyticsRangeSerializer], responses={200: AnalyticsSerializer})
    def get(self, request):
        period = AnalyticsRangeSerializer(data=request.query_params)
        period.is_valid(raise_exception=True)
        start, end = period.validated_data["from"], period.validated_data["to"]
        report = cache.get_or_compute(f"{start}:{end}", lambda: _compute(start, end))
        return Response(report)


def _compute(start, end) -> dict:
    median, delivered = queries.median_hours_to_delivery(start, end)
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "episodes_per_day": queries.episodes_per_day(start, end),
        "top_tasks_by_good_episodes": queries.top_tasks_by_good_episodes(start, end),
        "requests": {
            "by_status": queries.requests_by_status(start, end),
            "median_hours_to_delivery": median,
            "delivered_count": delivered,
        },
    }
