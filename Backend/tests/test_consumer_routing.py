from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from workers.consumer import handle_message


class ConsumerRoutingTests(unittest.TestCase):
    def test_article_event_routes_to_ai_processor(self) -> None:
        queue = MagicMock()
        event = {"event_type": "raw_collected"}
        result = {"source": "news", "external_id": "1"}
        with (
            patch("workers.consumer.process_event", return_value=result) as article,
        ):
            self.assertTrue(handle_message(queue, "receipt-1", event))
        article.assert_called_once_with(event, persist=True, sample_name=None)
        queue.delete.assert_called_once_with("receipt-1")

    def test_influencer_response_event_is_not_processed_by_article_worker(self) -> None:
        queue = MagicMock()
        event = {"event_type": "influencer_list_collected"}
        with (
            patch("workers.consumer.process_event") as article,
        ):
            self.assertFalse(handle_message(queue, "receipt-2", event))
        article.assert_not_called()
        queue.delete.assert_not_called()

    def test_legacy_raw_influencer_event_is_acknowledged_without_processing(self) -> None:
        queue = MagicMock()
        event = {
            "event_type": "raw_collected",
            "source": "x_influencer_discovery",
            "content_type": "influencer",
        }
        with patch("workers.consumer.process_event") as article:
            self.assertTrue(handle_message(queue, "receipt-legacy", event))
        article.assert_not_called()
        queue.delete.assert_called_once_with("receipt-legacy")


if __name__ == "__main__":
    unittest.main()
