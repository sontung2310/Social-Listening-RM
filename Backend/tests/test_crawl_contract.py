from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from flask import Blueprint, Flask

from api.crawl import _parse_crawl_body, register_crawl_routes
from publishers.command_sqs import build_crawl_command


class CrawlContractTests(unittest.TestCase):
    def test_typed_content_request(self) -> None:
        parsed, error = _parse_crawl_body(
            {
                "task_type": "content_crawl",
                "input": {"query": "AI marketing", "source": "news", "limit": 5},
            }
        )
        self.assertIsNone(error)
        self.assertEqual(parsed["task_type"], "content_crawl")
        self.assertEqual(parsed["input"]["query"], "AI marketing")

    def test_influencer_requires_complete_request(self) -> None:
        parsed, error = _parse_crawl_body(
            {"task_type": "influencer_discovery", "input": {"topic": "Marketing"}}
        )
        self.assertIsNone(parsed)
        self.assertEqual(error[1], 400)
        self.assertIn("company_id", error[0]["error"])

    def test_influencer_normalizes_complete_request(self) -> None:
        parsed, error = _parse_crawl_body(
            {
                "task_type": "influencer_discovery",
                "input": {
                    "company_id": "company-1",
                    "company_name": " Marketing   Eye ",
                    "company_domain": "Example.COM",
                    "company_summary": " A marketing agency ",
                    "field": " Retail ",
                    "related_terms": [" fashion ", "ecommerce"],
                    "platform": "X",
                    "limit": 10,
                },
            }
        )
        self.assertIsNone(error)
        self.assertEqual(parsed["input"]["company_id"], "company-1")
        self.assertEqual(parsed["input"]["company_name"], "Marketing Eye")
        self.assertEqual(parsed["input"]["company_domain"], "example.com")
        self.assertEqual(parsed["input"]["platform"], "x")
        self.assertEqual(parsed["input"]["related_terms"], ["fashion", "ecommerce"])

    def test_command_publisher_uses_typed_envelope(self) -> None:
        body = build_crawl_command(
            job_id="job-1",
            task_type="content_crawl",
            input_data={"query": "AI", "source": "all", "limit": 3},
        )
        self.assertEqual(body["task_type"], "content_crawl")
        self.assertEqual(body["input"]["query"], "AI")

    def test_start_route_forwards_each_task_type_without_crossing(self) -> None:
        app = Flask(__name__)
        blueprint = Blueprint("crawl_publish_test", __name__)
        register_crawl_routes(blueprint)
        app.register_blueprint(blueprint)
        db = {"crawl_jobs": MagicMock()}

        influencer_input = {
            "company_id": "company-1",
            "company_name": "Marketing Eye",
            "company_domain": "marketingeye.com.au",
            "company_summary": "A marketing agency helping brands grow.",
            "field": "Marketing",
            "related_terms": ["SEO"],
            "platform": "x",
            "limit": 10,
        }
        with (
            patch("api.crawl.get_mongo_db", return_value=db),
            patch("api.crawl.publish_crawl_command") as publish,
        ):
            content_response = app.test_client().post(
                "/crawl/",
                json={
                    "task_type": "content_crawl",
                    "input": {"query": "AI", "source": "news", "limit": 3},
                },
            )
            influencer_response = app.test_client().post(
                "/crawl/",
                json={"task_type": "influencer_discovery", "input": influencer_input},
            )

        self.assertEqual(content_response.status_code, 202)
        self.assertEqual(influencer_response.status_code, 202)
        self.assertEqual(
            [call.kwargs["task_type"] for call in publish.call_args_list],
            ["content_crawl", "influencer_discovery"],
        )
        self.assertEqual(publish.call_args_list[0].kwargs["input_data"]["query"], "AI")
        self.assertEqual(
            publish.call_args_list[1].kwargs["input_data"]["company_id"], "company-1"
        )

    def test_influencer_status_proxies_to_dct_task_id(self) -> None:
        app = Flask(__name__)
        blueprint = Blueprint("crawl_test", __name__)
        register_crawl_routes(blueprint)
        app.register_blueprint(blueprint)
        db = {"crawl_jobs": MagicMock()}
        db["crawl_jobs"].find_one.return_value = {
            "job_id": "pace-job-1",
            "task_type": "influencer_discovery",
            "dct_task_id": "dct-task-1",
        }
        response = MagicMock(status_code=200)
        response.json.return_value = {"task_id": "dct-task-1", "status": "completed", "progress": {}}
        with (
            patch("api.crawl.get_mongo_db", return_value=db),
            patch("api.crawl.requests.get", return_value=response) as dct_get,
        ):
            result = app.test_client().get("/crawl/pace-job-1/")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["status"], "completed")
        self.assertEqual(result.get_json()["dct_task_id"], "dct-task-1")
        dct_get.assert_called_once()
        self.assertEqual(dct_get.call_args.args[0], "http://127.0.0.1:8001/crawl/dct-task-1")


if __name__ == "__main__":
    unittest.main()
