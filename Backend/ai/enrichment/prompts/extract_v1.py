"""Call B — keywords + optional summary extraction prompt (v1.3).

v1.2 over-tightened noise rules (awkward fragments / empty lists) and pushed
long summaries toward detail hallucinations. v1.3 restores clearer word-cloud
guidance and strict faithfulness for summaries.
"""
from __future__ import annotations

from typing import Dict, List

VERSION = "extract_v1.3"


def system_prompt(*, summarize: bool) -> str:
    summary_rules = (
        "Write a faithful summary in 1–2 short sentences covering the central claim or event. "
        "Prefer a high-level thesis over stacking many specifics. "
        "ONLY state facts explicitly present in the text — no invented names, numbers, "
        "titles, companies, outcomes, or causal links. If unsure about a detail, omit it. "
        "Do not merely quote the opening line. "
        'Use "" only for greetings, one-word reactions, or text too thin to summarize.'
        if summarize
        else 'Set "summary" to exactly "".'
    )
    return f"""You are a keyword extractor for a social-listening word cloud. English multi-source UGC.

Your ONLY job: extract ranked keyphrases and optionally a short summary. Output one JSON object. No markdown. No commentary.

## Keywords
- Return 5–12 items when possible; fewer OK if text is short (never invent to pad the list)
- Short but meaningful text: return 1–3 strongest terms (never an empty list if a useful term exists)
- Each: {{"term":"...","score":0.0-1.0}} ranked by centrality to the whole text
- lowercase
- Prefer distinctive 1–2 word noun phrases (3 words max) that would stand alone in a word cloud
- Every term MUST be an exact contiguous lowercase substring of the input (no synonyms or paraphrases)
- Prefer complete natural phrases (e.g. "ai video", "affiliate sales") — not broken fragments ("use made ai", "for 2026", "data actually shows")
- Hashtags: keep the word without "#"; drop @handles and URLs
- No stopword-only terms; drop near-duplicate stems (keep the more informative form)

## Summary
{summary_rules}

## Output schema (exact keys)
{{"keywords":[{{"term":"content marketing","score":0.9}}],"summary":""}}
"""


def few_shots(*, summarize: bool) -> List[Dict[str, str]]:
    summary_out = (
        "A marketer explains how short-form video improved lead quality for a B2B SaaS launch."
        if summarize
        else ""
    )
    return [
        {
            "role": "user",
            "content": (
                "Extract from this text (summarize="
                + ("true" if summarize else "false")
                + "):\n"
                "We ran a LinkedIn content marketing campaign with short-form video and saw "
                "lead quality jump 30% for our B2B SaaS product launch."
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"keywords":['
                '{"term":"content marketing","score":0.95},'
                '{"term":"short-form video","score":0.9},'
                '{"term":"lead quality","score":0.85},'
                '{"term":"b2b saas","score":0.8},'
                '{"term":"product launch","score":0.75}'
                f'],"summary":"{summary_out}"}}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract from this text (summarize="
                + ("true" if summarize else "false")
                + "):\n"
                "The city proposes a driverless metro expansion to connect the rail network "
                "with downtown jobs, but residents worry about safety and cost overruns."
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"keywords":['
                '{"term":"driverless metro","score":0.95},'
                '{"term":"rail network","score":0.85},'
                '{"term":"safety","score":0.75},'
                '{"term":"cost overruns","score":0.7}'
                '],"summary":"'
                + (
                    "A city proposal for driverless metro expansion raises resident concerns about safety and cost overruns."
                    if summarize
                    else ""
                )
                + '"}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract from this text (summarize="
                + ("true" if summarize else "false")
                + "):\n"
                "use made ai video own me #love #music #song #art"
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"keywords":['
                '{"term":"ai video","score":0.95},'
                '{"term":"love","score":0.7},'
                '{"term":"music","score":0.7},'
                '{"term":"song","score":0.65},'
                '{"term":"art","score":0.65}'
                '],"summary":""}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract from this text (summarize="
                + ("true" if summarize else "false")
                + "):\n"
                "2030 dan AI. Part 2 #edukasitimothy #timothyronald #trending #2030 #artificialintelligence"
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"keywords":['
                '{"term":"artificialintelligence","score":0.9},'
                '{"term":"2030","score":0.85},'
                '{"term":"trending","score":0.5}'
                '],"summary":""}'
            ),
        },
    ]


def build_messages(text: str, *, summarize: bool) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt(summarize=summarize)}
    ]
    messages.extend(few_shots(summarize=summarize))
    messages.append(
        {
            "role": "user",
            "content": (
                f"Extract from this text (summarize={'true' if summarize else 'false'}):\n{text}"
            ),
        }
    )
    return messages


def meta() -> Dict[str, str]:
    return {"prompt_version": VERSION}
