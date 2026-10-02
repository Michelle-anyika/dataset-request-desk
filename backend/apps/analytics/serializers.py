from datetime import timedelta

from rest_framework import serializers

from apps.core.dates import business_today
from apps.core.query import QueryParamsSerializer

MAX_RANGE_DAYS = 366  # bounded cost: at most a year per query
DEFAULT_RANGE_DAYS = 30


class AnalyticsRangeSerializer(QueryParamsSerializer):
    """``from`` and ``to`` are inclusive business dates (Kigali). Defaults: the last 30 days, ending today."""

    pagination = False

    def get_fields(self):
        # "from" is a Python keyword, so the fields are declared here rather than as class attributes.
        return {
            "from": serializers.DateField(required=False, help_text="Inclusive start date (Kigali)."),
            "to": serializers.DateField(
                required=False,
                help_text=f"Inclusive end date (Kigali). The range is at most {MAX_RANGE_DAYS} days.",
            ),
        }

    def validate(self, attrs):
        end = attrs.get("to") or business_today()
        start = attrs.get("from") or end - timedelta(days=DEFAULT_RANGE_DAYS - 1)
        if start > end:
            raise serializers.ValidationError({"from": ["The start date is after the end date."]})
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            raise serializers.ValidationError({"to": [f"The range can be at most {MAX_RANGE_DAYS} days."]})
        return {"from": start, "to": end}


class DayCountSerializer(serializers.Serializer):
    date = serializers.DateField()
    robot_id = serializers.CharField()
    episodes = serializers.IntegerField()


class TaskCountSerializer(serializers.Serializer):
    task_name = serializers.CharField()
    good_episodes = serializers.IntegerField()


class FulfilmentSerializer(serializers.Serializer):
    by_status = serializers.DictField(child=serializers.IntegerField())
    median_hours_to_delivery = serializers.FloatField(allow_null=True)
    delivered_count = serializers.IntegerField(help_text="Delivered requests the median is based on.")


class AnalyticsSerializer(serializers.Serializer):
    range = AnalyticsRangeSerializer()
    episodes_per_day = DayCountSerializer(many=True)
    top_tasks_by_good_episodes = TaskCountSerializer(many=True)
    requests = FulfilmentSerializer()
