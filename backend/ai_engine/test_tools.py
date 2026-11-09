from django.test import SimpleTestCase

from ai_engine.tools import (
    get_database_metrics,
    get_recent_deployments,
    get_recent_logs,
    get_service_health,
)


class ReadOnlyToolTests(SimpleTestCase):
    def test_service_health_returns_demo_evidence(self):
        result = get_service_health("university-website")

        self.assertEqual(result["http_status"], 503)
        self.assertEqual(result["cpu_usage"], 35)

    def test_database_metrics_returns_demo_evidence(self):
        result = get_database_metrics("university-website")

        self.assertEqual(result["db_connection_usage"], 98)

    def test_logs_are_returned_as_data(self):
        result = get_recent_logs("university-website")

        self.assertTrue(result["logs"])

    def test_deployments_are_returned_as_data(self):
        result = get_recent_deployments("university-website")

        self.assertTrue(result["recent_deployment"])
        self.assertTrue(result["deployments"])

    def test_unknown_service_is_rejected(self):
        for tool in [
            get_service_health,
            get_database_metrics,
            get_recent_logs,
            get_recent_deployments,
        ]:
            self.assertEqual(
                tool("another-customer-service"),
                {"error": "Service not found or not authorized"},
            )
