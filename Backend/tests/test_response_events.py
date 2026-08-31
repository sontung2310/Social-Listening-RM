from __future__ import annotations

import unittest

from workers.events import (
    EventValidationError,
    validate_event,
)


class ResponseEventTests(unittest.TestCase):
    def test_article_event(self) -> None:
        event = {
            "schema_version": 1,
            "event_type": "raw_collected",
            "content_type": "post",
            "source": "newsapi",
            "external_id": "p1",
            "payload": {},
        }
        self.assertIs(validate_event(event), event)

    def test_influencer_response_event_is_rejected(self) -> None:
        with self.assertRaises(EventValidationError):
            validate_event(
                {
                    "schema_version": 1,
                    "event_type": "influencer_list_collected",
                    "content_type": "post",
                    "source": "newsapi",
                    "external_id": "p1",
                    "payload": {},
                }
            )

if __name__ == "__main__":
    unittest.main()
