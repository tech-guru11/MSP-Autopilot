from unittest.mock import patch

from accounts.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase


class HealthEndpointTests(TestCase):
    def test_health_reports_database_status(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertTrue(response.json()["database"])

    def test_request_id_is_echoed(self):
        response = self.client.get(
            "/health/",
            HTTP_X_REQUEST_ID="test-request-id",
        )

        self.assertEqual(response["X-Request-ID"], "test-request-id")


class TaskStatusEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="engineer",
            password="test-password",
        )
        self.client.force_authenticate(self.user)

    @patch("config.views.AsyncResult")
    def test_task_status_returns_success_result(self, async_result):
        result = async_result.return_value
        result.state = "SUCCESS"
        result.successful.return_value = True
        result.failed.return_value = False
        result.result = {"investigation_id": "investigation-1"}

        response = self.client.get("/api/tasks/task-1/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["task_id"], "task-1")
        self.assertEqual(response.data["state"], "SUCCESS")
        self.assertEqual(
            response.data["result"],
            {"investigation_id": "investigation-1"},
        )

    @patch("config.views.AsyncResult")
    def test_task_status_returns_failure_error(self, async_result):
        result = async_result.return_value
        result.state = "FAILURE"
        result.successful.return_value = False
        result.failed.return_value = True
        result.result = RuntimeError("diagnostic failed")

        response = self.client.get("/api/tasks/task-2/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "FAILURE")
        self.assertEqual(response.data["error"], "diagnostic failed")

    def test_task_status_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.get("/api/tasks/task-3/")

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
