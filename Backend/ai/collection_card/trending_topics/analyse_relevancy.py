import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gpt
import json

def relevancy_rag(context: dict, trending_topics: list[str]):
    company = context["name"]
    description = context["description"]
    competitors = ", ".join(context["competitors"])
    topics = "\n".join(trending_topics)

    prompt = f"""
You are an AI market analyst. Your job is to assess which external trending topics are most relevant to {company}.

Company description:
{description}

Competitors:
{competitors}

trending topics to evaluate:
{topics}

Return ONLY a valid JSON array with NO additional text. Each topic should have a relevance score between 0.0 and 1.0.

You MUST score STRICTLY. If a topic is vague, random, unrelated to  the company's industry, or you cannot determine relevance from the company description, give it a LOW score (≤ 0.30).

Scoring rubric:
- 0.80 to 1.00 → very clearly about this company, its product space, its competitors, or a market force that directly affects it.
- 0.50 to 0.79 → possibly relevant but not certain, or only partially overlapping.
- 0.20 to 0.49 → weak / indirect relevance.
- 0.00 to 0.19 → unrelated, nonsense, too short, or insufficient information.

Important rules:
- Do NOT invent relevance.
- Topics that look like placeholders (e.g. "a", "b", "c", "test", "sample") MUST get ≤ 0.10.
- If the topic is too generic (e.g. "news", "technology"), give ≤ 0.30.
- At least HALF of the topics must be ≤ 0.50.
Format:
[
  {{"topic": "relevance": 0.95}},
  {{"topic": " "relevance": 0.89}}
]
"""

    try:
        analysis = gpt.load_model(prompt, max_tokens=2000, temperature=0.2, stream=False)
        
        # Parse the JSON string into a Python list
        result = json.loads(analysis)
        
        # Validate it's actually a list
        if not isinstance(result, list):
            raise ValueError(f"Expected list, got {type(result)}")
        
        return result 
        
    except json.JSONDecodeError as e:
        raise ValueError(f"GPT returned invalid JSON: {e}\nResponse: {analysis}")
    except Exception as e:
        raise RuntimeError(f"Error during analysis: {e}")