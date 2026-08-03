# Pace-Unit\AI\collection_card\gpt.py

from groq import Groq
import os
import time
import random
from openai import RateLimitError
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

def safe_api_call(fn, *args, **kwargs):
    """
    Wraps any Groq/OpenAI API call and retries automatically
    when a rate-limit (HTTP 429) occurs.
    """
    max_retries = 5
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except RateLimitError as e:
            wait = 2 * (attempt + 1) + random.random()
            print(f"[RateLimit] {e}. Waiting {wait:.1f}s...")
            time.sleep(wait)
        except Exception as e:
            print(f"[API Error] {e}")
            raise
    raise RuntimeError("Exceeded maximum retries (rate limits).")


def load_model(prompt, max_tokens=256, temperature=1.0, stream=True):
    """
    Generate text using Groq API with streaming support
    Args:
        prompt: The user's input text
        max_tokens: Maximum number of tokens to generate
        temperature: Sampling temperature
        stream: Whether to stream output token by token
    """
    
    # Initialize Groq client
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in AI.env")
    client = Groq(api_key=api_key)
    
    # Model selection (equivalent to your 120B model)
    model_id = "openai/gpt-oss-20b"  # Closest to 120B, or use "llama3-8b-8192" for faster
    
    # Create completion
    try:
        completion = safe_api_call(
            client.chat.completions.create,
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
    )
    except Exception as e:
        print(f"[Groq API Error] {e}")
        return "Summary unavailable due to rate limit or API error."

    
    if stream:
        # Stream output token by token (just like your TextIteratorStreamer)
        generated_text = ""
        for chunk in completion:
            content = chunk.choices[0].delta.content or ""
            generated_text += content
        
        print()  # New line at end
        return generated_text
    else:
        # Non-streaming output
        generated_text = completion.choices[0].message.content
        return generated_text
