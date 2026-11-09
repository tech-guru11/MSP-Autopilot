from django.test import SimpleTestCase

from ai_engine.diagnostics import investigate_incident


class DiagnosticEngineTests(SimpleTestCase):
    def test_database_connection_exhaustion(self):
        evidence = {
            "observations": {
                "http_status": 503,
                "db_connection_usage": 98,
                "cpu_usage": 35,
                "recent_deployment": True,
                "log_errors": True,
            }
        }

        result = investigate_incident(evidence)
        titles = [item.title for item in result.hypotheses]

        self.assertIn(
            "Possible database connection exhaustion",
            titles,
        )
        self.assertIn(
            "Possible deployment-related regression",
            titles,
        )
        self.assertTrue(result.evidence)
        self.assertEqual(result.recommendation.risk, "low")
        self.assertFalse(result.recommendation.requires_approval)
        self.assertTrue(result.verification_steps)
        self.assertTrue(result.missing_information)

    def test_cpu_saturation(self):
        result = investigate_incident(
            {
                "observations": {
                    "cpu_usage": 99,
                    "http_status": 200,
                }
            }
        )

        self.assertEqual(
            result.hypotheses[0].title,
            "Possible CPU saturation",
        )
        self.assertEqual(result.hypotheses[0].confidence, "high")

    def test_deployment_regression(self):
        result = investigate_incident(
            {
                "observations": {
                    "http_status": 503,
                    "recent_deployment": True,
                }
            }
        )

        titles = [item.title for item in result.hypotheses]

        self.assertIn(
            "Possible deployment-related regression",
            titles,
        )
        self.assertEqual(result.hypotheses[0].confidence, "medium")

    def test_dns_failure(self):
        result = investigate_incident(
            {
                "observations": {
                    "dns_failure": True,
                    "http_status": 503,
                }
            }
        )

        titles = [item.title for item in result.hypotheses]

        self.assertIn(
            "Possible DNS resolution failure",
            titles,
        )

    def test_insufficient_evidence_reports_uncertainty(self):
        result = investigate_incident({"observations": {"http_status": 503}})

        self.assertEqual(
            result.hypotheses[0].title,
            "Cause not established",
        )
        self.assertEqual(result.hypotheses[0].confidence, "low")
        self.assertIn(
            "Collect application error logs around the incident.",
            result.missing_information,
        )
        self.assertIn(
            "Collect database connection usage and timeout metrics.",
            result.missing_information,
        )

    def test_empty_evidence_is_handled(self):
        result = investigate_incident({})

        self.assertEqual(
            result.hypotheses[0].title,
            "Cause not established",
        )
        self.assertTrue(result.missing_information)
        self.assertEqual(result.evidence, [])

    def test_hypothesis_sources_reference_collected_evidence(self):
        result = investigate_incident(
            {
                "observations": {
                    "http_status": 503,
                    "db_connection_usage": 98,
                    "recent_deployment": True,
                }
            }
        )
        evidence_sources = {item.source for item in result.evidence}

        for hypothesis in result.hypotheses:
            for source in hypothesis.evidence_sources:
                self.assertIn(source, evidence_sources)

    def test_result_serializes_to_json_compatible_data(self):
        result = investigate_incident({"observations": {"http_status": 503}})

        payload = result.model_dump()

        self.assertEqual(payload["severity_assessment"], "P1")
        self.assertIn("recommendation", payload)
        self.assertIn("missing_information", payload)
