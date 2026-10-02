"""Strict query parameters: unknown, blank or repeated ones are a 400, never silently ignored.

DRF's defaults treat query strings like HTML forms: an unknown parameter is ignored, a blank one counts as
absent, and a repeated one keeps its last value. So ``?stauts=delivered`` (a typo) returned the whole
unfiltered list with a 200, an answer to a question nobody asked. Found by Schemathesis.
"""

from rest_framework import serializers

PAGINATION = frozenset({"page", "page_size"})
MULTI_VALUE = (serializers.MultipleChoiceField, serializers.ListField)


class QueryParamsSerializer(serializers.Serializer):
    """Base for every query-parameter serializer. ``allowed_extra``: names validated elsewhere."""

    allowed_extra = PAGINATION  # lists are paginated; set to frozenset() where nothing is

    def to_internal_value(self, data):
        errors = {}
        for name in data:
            values = data.getlist(name) if hasattr(data, "getlist") else [data[name]]
            field = self.fields.get(name)
            if field is None:
                if name not in self.allowed_extra:
                    errors[name] = ["Unknown query parameter."]
            elif len(values) > 1 and not isinstance(field, MULTI_VALUE):
                errors[name] = ["Give this parameter only once."]
            elif "" in values:
                errors[name] = ["This field may not be blank."]
        if errors:
            raise serializers.ValidationError(errors)
        return super().to_internal_value(data)


class BooleanParam(serializers.ChoiceField):
    """``true`` or ``false``, exactly. (DRF's BooleanField reads a missing query value as False.)"""

    def __init__(self, **kwargs):
        super().__init__(choices=["true", "false"], required=False, **kwargs)
