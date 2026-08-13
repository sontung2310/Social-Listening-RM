"""Call A — sentiment + topic classification prompt (v1.2, nano-tuned)."""
from __future__ import annotations

from typing import Dict, List

from ai.enrichment.taxonomy import PROMPT_VERSION, taxonomy_prompt_block

VERSION = "classify_v1.2"


def system_prompt() -> str:
    return f"""You are a social-listening classifier for English user-generated content from multiple sources (X/Twitter, Reddit, YouTube, news, blogs, web).

Your ONLY job: assign sentiment and exactly one topic. Output a single JSON object. No markdown. No commentary.

## Sentiment
- label: exactly one of positive | neutral | negative
- score: confidence from 0.0 to 1.0
Rules:
- Evidence-driven at utterance level: praise, frustration, complaint, ridicule, apology, profanity usually indicate positive/negative even when the text is very short
- Promotional, celebratory, aspirational language → positive unless clearly sarcastic
- Sarcasm or ridicule that attacks something → lean negative
- Mixed sentiment → choose dominant polarity by main object / communicative intent (do not average)
- Short length does NOT imply neutral (e.g. "genius" → positive; "never arrives / keeps getting stuck" → negative)
- Factual reporting without clear opinion → neutral

## Topic (exactly one)
Choose from this closed list only:
{taxonomy_prompt_block()}

Decision procedure (follow in order):
1) Identify the primary subject (what the text is mainly about).
2) Identify communicative intent: reporting, analysis, feedback, promotion, technical instruction, commercial/ops discussion, or networking/community.
3) Pick the narrowest supported taxonomy label for that primary subject.
4) If none fit with reasonable confidence → Other with low topic_confidence.

Primary-subject rule: classify what the text is mainly about, not a secondary mention or the source type. Source provenance does not determine topic.

Critical anti-bias rules:
- Do NOT choose Marketing merely because the text mentions marketing, social media, visibility, influencers, ads, SEO, or growth as one bullet among several topics.
- Do NOT choose Marketing for founder/community networking posts that list many fields including marketing.
- Do NOT choose Marketing for product/feature announcements where promotion is secondary to the product/update itself → Product (or Technology if the subject is the technical system).
- Do NOT choose News merely because the source is a news site; News requires press-style current-event reporting as the main point.

Disambiguation:
- Campaigns, ads, branding, growth marketing, customer acquisition as the MAIN point → Marketing
- Features, UX, releases, roadmap, support, specific app/game/product experience → Product
- Hiring, unemployment, labor markets, outsourcing, funding, pricing, partnerships, competitors, earnings, commercial regulation → Business
- Systems, software behavior, AI/models/prompts, technical failures, engineering capabilities, programming → Technology
- Press-style reporting of a current event / dated market announcement as the main point → News
- Business vs Technology: jobs/markets/costs framing → Business; how the system/model works → Technology
- Technology vs Product: general tech/AI/tools → Technology; named/clear product feature-UX-support → Product
- Marketing vs Business: campaign/branding/acquisition → Marketing; company ops/finance/hiring/earnings → Business
- Product vs Marketing: the thing used/discussed → Product; the promotion/distribution strategy → Marketing
- Political/legal/ideological analysis without current-event reporting → Other (not News/Marketing)
- Too short to establish topic → Other (still classify explicit sentiment)

## Output schema (exact keys)
{{"sentiment":{{"label":"neutral","score":0.0}},"topic":"Other","topic_confidence":0.0}}
"""


def few_shots() -> List[Dict[str, str]]:
    return [
        {
            "role": "user",
            "content": (
                "Classify this text:\n"
                "Ugh this onboarding flow is a nightmare. Spent 40 minutes and still can't find the export button."
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"sentiment":{"label":"negative","score":0.92},'
                '"topic":"Product","topic_confidence":0.88}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Classify this text:\n"
                "Tech giant announces $2B funding round to expand AI cloud services across Europe."
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"sentiment":{"label":"neutral","score":0.8},'
                '"topic":"Business","topic_confidence":0.75}'
            ),
        },
        {
            "role": "user",
            "content": "Classify this text:\ngenius",
        },
        {
            "role": "assistant",
            "content": (
                '{"sentiment":{"label":"positive","score":0.9},'
                '"topic":"Other","topic_confidence":0.2}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Classify this text:\n"
                "My prompt keeps getting stuck and the agent never finishes the task."
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"sentiment":{"label":"negative","score":0.9},'
                '"topic":"Technology","topic_confidence":0.82}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Classify this text:\n"
                "Hey founders! Looking to connect with more people building in: Tech, Design, "
                "SaaS, Marketing, AI/ML, Sales. Share your project below."
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"sentiment":{"label":"positive","score":0.75},'
                '"topic":"Business","topic_confidence":0.7}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Classify this text:\n"
                "BIG GOOGLE SEARCH UPDATE Everyone can now claim their social profiles in "
                "Google Search Console without needing a domain first."
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"sentiment":{"label":"positive","score":0.7},'
                '"topic":"Product","topic_confidence":0.8}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Classify this text:\n"
                "use made ai video own me #love #music #song #art"
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"sentiment":{"label":"positive","score":0.65},'
                '"topic":"Technology","topic_confidence":0.55}'
            ),
        },
    ]


def build_messages(text: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt()}]
    messages.extend(few_shots())
    messages.append(
        {
            "role": "user",
            "content": f"Classify this text:\n{text}",
        }
    )
    return messages


def meta() -> Dict[str, str]:
    return {"prompt_version": VERSION, "bundle": PROMPT_VERSION}
