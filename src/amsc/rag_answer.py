"""The answer model: grounded generation over an assembled context.

The model sees the question and the labelled context blocks, nothing else --
no document beyond the retrieved passages, no chunking metadata, no key. It
must answer from the blocks, cite them by label, and say plainly when they
do not contain the answer. The reply is JSON so the chat can show which
sources were actually used and whether the model judged them sufficient;
a reply that is not JSON is still shown, as text, with ``sufficient`` unknown
rather than guessed.

Transport is the same OpenAI-compatible chat-completions contract the
boundary judge uses; the model id is configuration. The key is read from
the environment at request time and never stored or logged.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from .rag_context import ContextBlock

DEFAULT_ANSWER_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"
DEFAULT_ANSWER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
PROMPT_VERSION = "rag-answer-v1"

SYSTEM_PROMPT = """Sen bir kurumsal doküman asistanısın. Kullanıcının sorusunu YALNIZCA sana verilen kaynak parçalara dayanarak cevaplarsın.

Kurallar:
- Cevabı yalnızca [S1], [S2] ... etiketli kaynaklardaki bilgilerle kur. Kaynaklarda olmayan hiçbir sayı, isim veya iddia ekleme.
- Kullandığın her bilgi için cümlenin sonunda kaynağı köşeli parantezle belirt, örn. "... 197 üyesi vardır [S1]."
- Birden fazla kaynak aynı konuyu anlatıyorsa birleştirerek cevapla.
- Kaynaklar soruyu cevaplamaya yetmiyorsa bunu açıkça söyle; tahmin yürütme.
- Türkçe, açık ve kısa cevap ver. Tablo verisi varsa rakamları olduğu gibi aktar.

Yanıtı SADECE şu JSON biçiminde ver (başka metin yazma):
{"answer": "<cevap metni, kaynak etiketleriyle>", "sources_used": ["S1", "S3"], "sufficient": true}

"sufficient": kaynaklar sorunun cevabını içeriyorsa true, içermiyorsa false."""


class AnswerProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    def chat(self, system: str, user: str) -> tuple[str, dict[str, Any]]: ...


@dataclass
class AnswerParse:
    answer: str
    sources_used: list[str]
    sufficient: bool | None
    raw: str
    parsed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources_used": list(self.sources_used),
            "sufficient": self.sufficient,
            "parsed": self.parsed,
        }


@dataclass
class AnswerResult:
    parse: AnswerParse
    model_id: str
    seconds: float
    usage: dict[str, Any] = field(default_factory=dict)
    prompt_version: str = PROMPT_VERSION


class OpenAICompatibleChatProvider:
    """``POST /chat/completions`` with a system and a user message."""

    def __init__(
        self,
        model: str = DEFAULT_ANSWER_MODEL,
        *,
        endpoint: str = DEFAULT_ANSWER_ENDPOINT,
        api_key_env: str = "OPENROUTER_API_KEY",
        temperature: float = 0.0,
        max_tokens: int = 900,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.calls = 0

    @property
    def model_id(self) -> str:
        return self.model

    def _key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise RuntimeError(
                f"{self.api_key_env} is not set; the answer model cannot run "
                "without it (and it is never stored)"
            )
        return key

    def chat(self, system: str, user: str) -> tuple[str, dict[str, Any]]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"answer endpoint returned HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RuntimeError(f"answer endpoint unreachable: {error}") from None
        self.calls += 1
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("answer endpoint returned an unexpected shape") from error
        return str(text), dict(payload.get("usage") or {})


def build_user_prompt(question: str, context_text: str) -> str:
    return (
        "KAYNAKLAR:\n\n"
        f"{context_text}\n\n"
        "SORU:\n"
        f"{question.strip()}\n\n"
        "Yalnızca yukarıdaki kaynaklara dayanarak JSON biçiminde cevap ver."
    )


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)
_LABEL = re.compile(r"\bS\d+\b")


def parse_answer(raw: str | None, labels: Sequence[str]) -> AnswerParse:
    """Strict-but-forgiving parse: JSON when present, text otherwise."""
    if raw is None:
        return AnswerParse("", [], None, "", False)
    valid = set(labels)
    match = _JSON_BLOCK.search(raw)
    if match:
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and "answer" in payload:
            answer = str(payload.get("answer") or "").strip()
            used = payload.get("sources_used")
            sources = [str(s) for s in used if str(s) in valid] if isinstance(used, list) else []
            if not sources:
                sources = sorted(set(_LABEL.findall(answer)) & valid, key=lambda s: int(s[1:]))
            sufficient = payload.get("sufficient")
            return AnswerParse(
                answer,
                sources,
                bool(sufficient) if isinstance(sufficient, bool) else None,
                raw,
                True,
            )
    text = raw.strip()
    cited = sorted(set(_LABEL.findall(text)) & valid, key=lambda s: int(s[1:]))
    return AnswerParse(text, cited, None, raw, False)


def answer(
    question: str,
    blocks: Sequence[ContextBlock],
    context_text: str,
    *,
    provider: AnswerProvider,
) -> AnswerResult:
    started = time.perf_counter()
    raw, usage = provider.chat(SYSTEM_PROMPT, build_user_prompt(question, context_text))
    parse = parse_answer(raw, [block.label for block in blocks])
    return AnswerResult(
        parse=parse,
        model_id=provider.model_id,
        seconds=round(time.perf_counter() - started, 3),
        usage=usage,
    )


def build_answer_provider(config: dict[str, Any]) -> AnswerProvider:
    return OpenAICompatibleChatProvider(
        str(config.get("model", DEFAULT_ANSWER_MODEL)),
        endpoint=str(config.get("endpoint", DEFAULT_ANSWER_ENDPOINT)),
        api_key_env=str(config.get("api_key_env", "OPENROUTER_API_KEY")),
        temperature=float(config.get("temperature", 0.0)),
        max_tokens=int(config.get("max_tokens", 900)),
        timeout_seconds=float(config.get("timeout_seconds", 120.0)),
    )
