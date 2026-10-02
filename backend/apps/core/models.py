from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


class IdempotencyKey(models.Model):
    """One POST made with an ``Idempotency-Key`` header, kept for a day so retries replay its response.

    A row without a response is still running. Failed requests are not kept: they changed nothing.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    key = models.CharField(max_length=255)
    fingerprint = models.CharField(max_length=64, help_text="SHA-256 of the method, path and body.")
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "idempotency_keys"
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="idempotency_key_per_user")]

    def __str__(self):
        return f"{self.key} ({self.response_status or 'running'})"
