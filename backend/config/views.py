from celery.result import AsyncResult
from django.db import connection
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.celery import app as celery_app


def health(request):
    database_ok = True

    try:
        connection.ensure_connection()
    except Exception:
        database_ok = False

    payload = {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
    }

    return JsonResponse(
        payload,
        status=200 if database_ok else 503,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def task_status(request, task_id):
    result = AsyncResult(task_id, app=celery_app)
    payload = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.successful():
        payload["result"] = result.result
    elif result.failed():
        payload["error"] = str(result.result)

    return Response(payload)
