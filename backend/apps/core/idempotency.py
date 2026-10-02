"""Idempotency keys for POST endpoints that create or change things.

A client that may retry (after a timeout, a double click, a dropped connection) sends an
``Idempotency-Key`` header, any unique string such as a UUID. The first request with that key runs and its
response is stored; a retry with the same key and the same body gets that stored response back, marked
``Idempotent-Replayed: true``, and does nothing again.

- The key is reserved (a committed row) *before* the work runs, and the database's unique constraint
  makes it race-free: of two concurrent requests with one key, one runs and the other gets 409.
- Reusing a key for a different body is a client bug: 422, never a silent replay of the wrong answer.
- Failed requests (any error) are forgotten: they changed nothing, so the client may fix and retry.
- Keys last 24 hours (``purge_idempotency_keys`` deletes older ones). Without the header, nothing changes.
"""

import hashlib
import json
from datetime import timedelta
from functools import wraps

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.response import Response

from apps.core.models import IdempotencyKey

HEADER = "Idempotency-Key"
TTL = timedelta(hours=24)
MAX_KEY_LENGTH = 255


class InvalidIdempotencyKey(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = f"{HEADER} must be 1-{MAX_KEY_LENGTH} printable ASCII characters."
    default_code = "invalid_idempotency_key"


class IdempotencyKeyInUse(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = f"A request with this {HEADER} is still being processed; retry shortly."
    default_code = "idempotency_key_in_use"


class IdempotencyKeyReused(exceptions.APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = f"This {HEADER} was already used for a different request."
    default_code = "idempotency_key_reused"


def idempotent(*methods: str):
    """Decorate a DRF view method so the given HTTP methods (default POST) honour ``Idempotency-Key``."""
    methods = {m.upper() for m in methods} or {"POST"}

    def decorator(view_method):
        @wraps(view_method)
        def wrapper(view, request, *args, **kwargs):
            key = request.headers.get(HEADER)
            if key is None or request.method not in methods:
                return view_method(view, request, *args, **kwargs)
            return run_once(request, key, lambda: view_method(view, request, *args, **kwargs))

        wrapper.idempotent_methods = methods  # read by the OpenAPI schema (apps.core.openapi)
        return wrapper

    return decorator


def run_once(request, key: str, handle) -> Response:
    if not (0 < len(key) <= MAX_KEY_LENGTH and key.isascii() and key.isprintable()):
        raise InvalidIdempotencyKey()

    fingerprint = _fingerprint(request)
    record, created = _reserve(request.user, key, fingerprint)
    if not created:
        return _replay(record, fingerprint)

    try:
        response = handle()
    except BaseException:
        record.delete()
        raise
    if response.status_code >= 400:
        record.delete()
        return response

    record.response_status = response.status_code
    record.response_body = response.data
    record.save(update_fields=["response_status", "response_body"])
    return response


def _reserve(user, key, fingerprint):
    IdempotencyKey.objects.filter(user=user, key=key, created_at__lt=timezone.now() - TTL).delete()
    try:
        with transaction.atomic():
            return IdempotencyKey.objects.create(user=user, key=key, fingerprint=fingerprint), True
    except IntegrityError:
        return IdempotencyKey.objects.get(user=user, key=key), False


def _replay(record, fingerprint):
    if record.response_status is None:
        raise IdempotencyKeyInUse()
    if record.fingerprint != fingerprint:
        raise IdempotencyKeyReused()
    response = Response(record.response_body, status=record.response_status)
    response["Idempotent-Replayed"] = "true"
    return response


def _fingerprint(request) -> str:
    """The same request means the same method, path and body; uploaded files are hashed by content."""
    digest = hashlib.sha256(f"{request.method} {request.path}\n".encode())
    data = request.data
    if hasattr(data, "getlist"):  # form or multipart
        for name in sorted(data):
            for value in data.getlist(name):
                digest.update(name.encode() + b"=")
                if hasattr(value, "chunks"):
                    for chunk in value.chunks():
                        digest.update(chunk)
                    value.seek(0)
                else:
                    digest.update(str(value).encode())
                digest.update(b"\n")
    else:
        digest.update(json.dumps(data, sort_keys=True, default=str).encode())
    return digest.hexdigest()


def purge_expired() -> int:
    deleted, _ = IdempotencyKey.objects.filter(created_at__lt=timezone.now() - TTL).delete()
    return deleted
