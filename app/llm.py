"""Provider-independent LLM layer.

Every provider implements one job: given a system prompt, a user prompt and a
Pydantic model, return a validated instance of that model.

- "anthropic" uses the native Anthropic SDK (structured outputs + refusal fallbacks).
- Every other provider uses the OpenAI-compatible Chat Completions API, which
  OpenAI, Gemini, Groq, OpenRouter, DeepSeek, Mistral, Together, Ollama,
  LM Studio, vLLM, etc. all expose. "custom" lets you point at any such endpoint.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Provider:
    label: str
    default_model: str
    base_url: str = ""
    key_env: str = ""
    needs_key: bool = True


PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider("Anthropic (Claude)", "claude-opus-5-5", key_env="ANTHROPIC_API_KEY"),
    "openai": Provider("OpenAI", "gpt-5", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "gemini": Provider("Google Gemini", "gemini-pro-latest",
                       "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    # Gemini on Vertex AI: billed to the Google Cloud project (Cloud credits), auth via `gcloud` login.
    "vertex": Provider("Google Vertex AI (Gemini, Cloud billing)", "google/gemini-3.5-flash", needs_key=False),
    "groq": Provider("Groq", "llama-3.3-70b-versatile", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": Provider("OpenRouter (any model)", "anthropic/claude-opus-5-5",
                           "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "deepseek": Provider("DeepSeek", "deepseek-chat", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "mistral": Provider("Mistral", "mistral-large-latest", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "ollama": Provider("Ollama (local)", "llama3.1", "http://localhost:11434/v1", needs_key=False),
    "lmstudio": Provider("LM Studio (local)", "local-model", "http://localhost:1234/v1", needs_key=False),
    "custom": Provider("Custom OpenAI-compatible", "", "", "LLM_API_KEY", needs_key=False),
}


class LLMRefused(Exception):
    pass


class LLMConfigError(Exception):
    pass


@dataclass
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key: str


_vertex_token: tuple[str, float] = ("", 0.0)


def _vertex_access_token() -> str:
    """Short-lived OAuth token from the local gcloud login, cached for 45 minutes."""
    global _vertex_token
    import shutil
    import subprocess
    import time

    tok, exp = _vertex_token
    if tok and time.time() < exp:
        return tok
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        raise LLMConfigError("gcloud CLI not found; install it and run `gcloud auth login` for Vertex AI")
    r = subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True, timeout=60)
    tok = r.stdout.strip()
    if r.returncode != 0 or not tok:
        raise LLMConfigError(f"Could not get a gcloud access token (run `gcloud auth login`): {r.stderr.strip()[:300]}")
    _vertex_token = (tok, time.time() + 45 * 60)
    return tok


def _vertex_base_url() -> str:
    project = os.getenv("VERTEX_PROJECT", "")
    if not project:
        raise LLMConfigError("Set VERTEX_PROJECT in .env to use Vertex AI")
    location = os.getenv("VERTEX_LOCATION", "global")
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    return f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"


def resolve_config(provider: str, model: str = "", base_url: str = "", api_key: str = "") -> LLMConfig:
    provider = provider or os.getenv("LLM_PROVIDER", "anthropic")
    p = PROVIDERS.get(provider)
    if p is None:
        raise LLMConfigError(f"Unknown provider '{provider}'")
    if provider == "vertex":
        model = model or os.getenv("LLM_MODEL", "") or p.default_model
        if "/" not in model:
            model = f"google/{model}"
        return LLMConfig(provider, model, base_url or _vertex_base_url(), _vertex_access_token())
    cfg = LLMConfig(
        provider=provider,
        model=model or os.getenv("LLM_MODEL", "") or p.default_model,
        base_url=base_url or p.base_url,
        api_key=api_key or (os.getenv(p.key_env, "") if p.key_env else "") or os.getenv("LLM_API_KEY", ""),
    )
    if not cfg.model:
        raise LLMConfigError("No model name set")
    if provider != "anthropic" and not cfg.base_url:
        raise LLMConfigError("No base URL set for the custom provider")
    if p.needs_key and not cfg.api_key:
        raise LLMConfigError(f"No API key for {p.label} (set it in the UI or {p.key_env} in .env)")
    return cfg


# ---------------------------------------------------------------- Anthropic
_anthropic_clients: dict[str, object] = {}


def _anthropic(cfg: LLMConfig, system: str, user: str, schema: type[T]) -> T:
    import anthropic

    client = _anthropic_clients.get(cfg.api_key)
    if client is None:
        client = anthropic.Anthropic(api_key=cfg.api_key or None)
        _anthropic_clients[cfg.api_key] = client
    response = client.beta.messages.parse(
        model=cfg.model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium"},
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )
    if response.stop_reason == "refusal":
        raise LLMRefused(getattr(response.stop_details, "explanation", "") or "model declined")
    if response.parsed_output is None:
        raise RuntimeError(f"No structured output (stop_reason={response.stop_reason})")
    return response.parsed_output


# --------------------------------------------------------- OpenAI-compatible
def _strict_schema(schema: type[BaseModel]) -> dict:
    s = schema.model_json_schema()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}).keys())
            for k in ("title", "default"):
                node.pop(k, None)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(s)
    return s


def _extract_json(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        return fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


# Remember which response_format each endpoint+model accepts, so we don't re-probe every email.
_format_mode: dict[tuple[str, str], str] = {}


def _openai_compatible(cfg: LLMConfig, system: str, user: str, schema: type[T]) -> T:
    import openai

    client = openai.OpenAI(api_key=cfg.api_key or "not-needed", base_url=cfg.base_url, timeout=300, max_retries=2)
    json_schema = _strict_schema(schema)
    sys_prompt = (f"{system}\n\nRespond with a single JSON object only — no prose, no code fences — "
                  f"matching this JSON Schema:\n{json.dumps(json_schema)}")
    formats = {
        "json_schema": {"type": "json_schema",
                        "json_schema": {"name": schema.__name__, "schema": json_schema, "strict": True}},
        "json_object": {"type": "json_object"},
        "none": None,
    }
    key = (cfg.base_url, cfg.model)
    order = [_format_mode[key]] if key in _format_mode else ["json_schema", "json_object", "none"]

    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}]
    last_err: Exception | None = None
    for mode in order:
        kwargs = {"model": cfg.model, "messages": messages}
        if formats[mode]:
            kwargs["response_format"] = formats[mode]
        try:
            resp = client.chat.completions.create(**kwargs)
        except openai.BadRequestError as e:  # endpoint/model doesn't support this response_format
            last_err = e
            continue
        _format_mode[key] = mode
        choice = resp.choices[0]
        if getattr(choice.message, "refusal", None):
            raise LLMRefused(choice.message.refusal)
        content = choice.message.content or ""
        try:
            return schema.model_validate_json(_extract_json(content))
        except ValidationError as e:
            # one repair attempt: show the model its own output and the validation error
            repair = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That JSON was invalid: {e}. Reply again with only the corrected JSON object."},
            ]
            kwargs["messages"] = repair
            resp = client.chat.completions.create(**kwargs)
            return schema.model_validate_json(_extract_json(resp.choices[0].message.content or ""))
    raise RuntimeError(f"Provider rejected every response format: {last_err}")


# ----------------------------------------------------------------- public API
def generate_structured(cfg: LLMConfig, system: str, user: str, schema: type[T]) -> T:
    if cfg.provider == "anthropic":
        return _anthropic(cfg, system, user, schema)
    return _openai_compatible(cfg, system, user, schema)


class _Ping(BaseModel):
    ok: bool
    model_name: str


def test(cfg: LLMConfig) -> str:
    r = generate_structured(cfg, "You are a connectivity check.",
                            'Return ok=true and model_name set to the name of the model you are.', _Ping)
    return r.model_name
