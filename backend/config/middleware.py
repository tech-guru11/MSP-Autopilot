import logging
import uuid
from contextvars import ContextVar

request_id_context = ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_context.get()
        return True


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = request_id
        token = request_id_context.set(request_id)

        try:
            response = self.get_response(request)
        finally:
            request_id_context.reset(token)

        response["X-Request-ID"] = request_id
        return response
