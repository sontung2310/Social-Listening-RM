"""OpenAI-compatible LLM client with OpenRouter → OpenAI failover."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from ai.enrichment.logging_util import log_step, preview
from ai.enrichment import settings as nlp_settings

_ENV_LOADED = False


def _ensure_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = Path(__file__).resolve().parent.parent / "AI.env"
    load_dotenv(env_path)
    # also allow Backend credentials
    backend_env = Path(__file__).resolve().parents[2] / "credentials" / "backend.env"
    if backend_env.exists():
        load_dotenv(backend_env, override=False)
    _ENV_LOADED = True


def _message_content(completion: Any) -> str:
    """Safely read chat completion content (OpenRouter free often returns empty choices)."""
    try:
        choices = getattr(completion, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if message is None:
            return ""
        return (getattr(message, "content", None) or "").strip()
    except Exception:
        return ""


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    latency_ms: float
    ok: bool
    error: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0


class LLMClient:
    """Chat completions via OpenRouter primary, OpenAI backup."""

    def __init__(self) -> None:
        _ensure_env()
        self.timeout_s = nlp_settings.get_timeout_ms() / 1000.0
        self.primary_model = nlp_settings.get_primary_model()
        self.backup_model = nlp_settings.get_backup_model()
        self.judge_model = nlp_settings.get_judge_model()
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY") or ""
        self.openai_key = os.getenv("OPENAI_API_KEY") or ""
        # Cumulative usage for cost accounting (enrichment only; judge uses same client)
        self.usage_prompt_tokens = 0
        self.usage_completion_tokens = 0
        self.usage_total_tokens = 0
        self.usage_reasoning_tokens = 0
        self.usage_calls_ok = 0
        self.usage_calls_fail = 0

    def reset_usage(self) -> None:
        self.usage_prompt_tokens = 0
        self.usage_completion_tokens = 0
        self.usage_total_tokens = 0
        self.usage_reasoning_tokens = 0
        self.usage_calls_ok = 0
        self.usage_calls_fail = 0

    def usage_snapshot(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.usage_prompt_tokens,
            "completion_tokens": self.usage_completion_tokens,
            "total_tokens": self.usage_total_tokens,
            "reasoning_tokens": self.usage_reasoning_tokens,
            "calls_ok": self.usage_calls_ok,
            "calls_fail": self.usage_calls_fail,
        }

    def _record_usage(self, completion: Any, resp: LLMResponse) -> LLMResponse:
        usage = getattr(completion, "usage", None)
        if usage is not None:
            resp.prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            resp.completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            resp.total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
            details = getattr(usage, "completion_tokens_details", None)
            if details is not None:
                resp.reasoning_tokens = int(getattr(details, "reasoning_tokens", 0) or 0)
            self.usage_prompt_tokens += resp.prompt_tokens
            self.usage_completion_tokens += resp.completion_tokens
            self.usage_total_tokens += resp.total_tokens
            self.usage_reasoning_tokens += resp.reasoning_tokens
        if resp.ok:
            self.usage_calls_ok += 1
        else:
            self.usage_calls_fail += 1
        return resp

    def _client(self, provider: str):
        from openai import OpenAI

        if provider == "openrouter":
            if not self.openrouter_key:
                raise ValueError("OPENROUTER_API_KEY not set")
            return OpenAI(
                api_key=self.openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=self.timeout_s,
                max_retries=0,
                default_headers={
                    "HTTP-Referer": "https://pace-unit.local",
                    "X-Title": "Pace-Unit Enrichment",
                },
            )
        if not self.openai_key:
            raise ValueError("OPENAI_API_KEY not set")
        return OpenAI(
            api_key=self.openai_key,
            timeout=self.timeout_s,
            max_retries=0,
        )

    def _is_retryable(self, exc: BaseException) -> bool:
        name = type(exc).__name__
        msg = str(exc).lower()
        if "timeout" in msg or "timed out" in msg:
            return True
        if "404" in msg or "unavailable" in msg or "no endpoints" in msg:
            return True
        if "429" in msg or "rate" in msg:
            return True
        if "402" in msg or "quota" in msg or "credit" in msg:
            return True
        if "503" in msg or "502" in msg or "500" in msg:
            return True
        if name in {"RateLimitError", "APITimeoutError", "InternalServerError", "APIConnectionError"}:
            return True
        return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 512,
        json_mode: bool = True,
        event_prefix: str = "CALL",
        force_provider: Optional[str] = None,
        force_model: Optional[str] = None,
    ) -> LLMResponse:
        """
        Try OpenRouter then OpenAI on retryable failure.
        force_provider/force_model used for judge (OpenAI Luna only).
        """
        if force_provider:
            chain: List[Tuple[str, str]] = [
                (force_provider, force_model or self.backup_model)
            ]
        else:
            prefer_openai = nlp_settings.get_prefer_openai_primary()
            openai_only = nlp_settings.get_openai_only()
            openrouter_only = (os.getenv("NLP_OPENROUTER_ONLY") or "").strip() in {
                "1",
                "true",
                "yes",
            }
            chain = []
            if openrouter_only and self.openrouter_key:
                chain.append(("openrouter", self.primary_model))
            elif openai_only and self.openai_key:
                chain.append(("openai", self.backup_model))
            elif prefer_openai and self.openai_key:
                chain.append(("openai", self.backup_model))
                if self.openrouter_key:
                    chain.append(("openrouter", self.primary_model))
            else:
                if self.openrouter_key:
                    chain.append(("openrouter", self.primary_model))
                if self.openai_key:
                    chain.append(("openai", self.backup_model))
            if not chain:
                return LLMResponse(
                    content="",
                    provider="none",
                    model="",
                    latency_ms=0.0,
                    ok=False,
                    error="No API keys configured",
                )

        last_error: Optional[str] = None
        for provider, model in chain:
            log_step(
                f"{event_prefix}_REQ",
                provider=provider,
                model=model,
                messages=len(messages),
                preview=preview(
                    next((m["content"] for m in reversed(messages) if m.get("role") == "user"), ""),
                    200,
                ),
            )
            t0 = time.perf_counter()
            try:
                client = self._client(provider)
                kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                }
                # GPT-5.x / Luna prefer max_completion_tokens; older models use max_tokens
                use_completion_tokens = any(
                    x in (model or "").lower()
                    for x in ("gpt-5", "luna", "o1", "o3", "o4")
                )
                if use_completion_tokens:
                    kwargs["max_completion_tokens"] = max_tokens
                    # Only gpt-5-nano needs minimal reasoning for JSON enrichment;
                    # do NOT set this on Luna / other GPT-5 judges (unsupported).
                    if "nano" in (model or "").lower():
                        kwargs["reasoning_effort"] = "minimal"
                else:
                    kwargs["temperature"] = temperature
                    kwargs["max_tokens"] = max_tokens
                if json_mode:
                    # OpenRouter / OpenAI JSON object mode when supported
                    kwargs["response_format"] = {"type": "json_object"}
                completion = client.chat.completions.create(**kwargs)
                content = _message_content(completion)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                if not content:
                    last_error = "empty_content"
                    log_step(
                        f"{event_prefix}_RES",
                        provider=provider,
                        model=model,
                        latency_ms=round(latency_ms, 1),
                        error="empty_content",
                    )
                    self._record_usage(
                        completion,
                        LLMResponse(
                            content="",
                            provider=provider,
                            model=model,
                            latency_ms=latency_ms,
                            ok=False,
                            error="empty_content",
                        ),
                    )
                    # GPT-5 reasoning models often burn the whole budget on reasoning
                    # with empty visible content — bump once and retry same provider.
                    if use_completion_tokens and max_tokens < 4096:
                        try:
                            t_retry = time.perf_counter()
                            bump_kwargs = dict(kwargs)
                            bump_kwargs["max_completion_tokens"] = max(max_tokens * 4, 2048)
                            if "nano" in (model or "").lower():
                                bump_kwargs["reasoning_effort"] = "minimal"
                            completion2 = client.chat.completions.create(**bump_kwargs)
                            content2 = _message_content(completion2)
                            latency2 = (time.perf_counter() - t_retry) * 1000.0
                            if content2:
                                log_step(
                                    f"{event_prefix}_RES",
                                    provider=provider,
                                    model=model,
                                    latency_ms=round(latency2, 1),
                                    preview=preview(content2, 240),
                                    note="bumped_completion_tokens",
                                )
                                return self._record_usage(
                                    completion2,
                                    LLMResponse(
                                        content=content2,
                                        provider=provider,
                                        model=model,
                                        latency_ms=latency2,
                                        ok=True,
                                    ),
                                )
                            self._record_usage(
                                completion2,
                                LLMResponse(
                                    content="",
                                    provider=provider,
                                    model=model,
                                    latency_ms=latency2,
                                    ok=False,
                                    error="empty_content",
                                ),
                            )
                        except Exception as bump_exc:
                            last_error = f"{type(bump_exc).__name__}: {bump_exc}"
                    continue
                log_step(
                    f"{event_prefix}_RES",
                    provider=provider,
                    model=model,
                    latency_ms=round(latency_ms, 1),
                    preview=preview(content, 240),
                )
                return self._record_usage(
                    completion,
                    LLMResponse(
                        content=content,
                        provider=provider,
                        model=model,
                        latency_ms=latency_ms,
                        ok=True,
                    ),
                )
            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                last_error = f"{type(exc).__name__}: {exc}"
                log_step(
                    f"{event_prefix}_RES",
                    provider=provider,
                    model=model,
                    latency_ms=round(latency_ms, 1),
                    error=preview(last_error, 200),
                )
                # retry without json_mode once on same provider if format unsupported
                if "response_format" in str(exc).lower() or "json" in str(exc).lower():
                    try:
                        t1 = time.perf_counter()
                        client = self._client(provider)
                        retry_kwargs: Dict[str, Any] = {
                            "model": model,
                            "messages": messages,
                        }
                        use_completion_tokens = any(
                            x in (model or "").lower()
                            for x in ("gpt-5", "luna", "o1", "o3", "o4")
                        )
                        if use_completion_tokens:
                            retry_kwargs["max_completion_tokens"] = max_tokens
                        else:
                            retry_kwargs["temperature"] = temperature
                            retry_kwargs["max_tokens"] = max_tokens
                        completion = client.chat.completions.create(**retry_kwargs)
                        content = _message_content(completion)
                        latency_ms = (time.perf_counter() - t1) * 1000.0
                        if content:
                            log_step(
                                f"{event_prefix}_RES",
                                provider=provider,
                                model=model,
                                latency_ms=round(latency_ms, 1),
                                preview=preview(content, 240),
                                note="no_json_mode",
                            )
                            return self._record_usage(
                                completion,
                                LLMResponse(
                                    content=content,
                                    provider=provider,
                                    model=model,
                                    latency_ms=latency_ms,
                                    ok=True,
                                ),
                            )
                    except Exception as exc2:
                        last_error = f"{type(exc2).__name__}: {exc2}"
                if force_provider or not self._is_retryable(exc):
                    # still try next in chain for non-forced unless last
                    if force_provider:
                        break
                    continue
                continue

        return LLMResponse(
            content="",
            provider=chain[-1][0] if chain else "none",
            model=chain[-1][1] if chain else "",
            latency_ms=0.0,
            ok=False,
            error=last_error or "unknown",
        )

    def judge_chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> LLMResponse:
        # Guidance / judge payloads are larger; allow a longer timeout.
        prev = self.timeout_s
        self.timeout_s = max(prev, 60.0)
        try:
            return self.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
                event_prefix="JUDGE",
                force_provider="openai",
                force_model=self.judge_model,
            )
        finally:
            self.timeout_s = prev
