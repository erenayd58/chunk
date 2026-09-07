from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TokenCounter(Protocol):
    @property
    def counter_id(self) -> str: ...

    def count(self, text: str) -> int: ...

    def split(self, text: str, max_tokens: int) -> list[str]: ...


class TiktokenTokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        try:
            import tiktoken
        except ImportError as exc:  # pragma: no cover - dependency error path
            raise RuntimeError("Install the 'tiktoken' package") from exc

        self._tiktoken = tiktoken
        self._encoding_name = encoding_name
        self._encoding = tiktoken.get_encoding(encoding_name)

    @property
    def counter_id(self) -> str:
        version = getattr(self._tiktoken, "__version__", "unknown")
        return f"tiktoken:{self._encoding_name}@{version}"

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))

    def split(self, text: str, max_tokens: int) -> list[str]:
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not text:
            return [""]

        pieces: list[str] = []
        cursor = 0
        while cursor < len(text):
            remainder = text[cursor:]
            if self.count(remainder) <= max_tokens:
                pieces.append(remainder)
                break

            low = 1
            high = len(remainder)
            best = 0
            while low <= high:
                midpoint = (low + high) // 2
                if self.count(remainder[:midpoint]) <= max_tokens:
                    best = midpoint
                    low = midpoint + 1
                else:
                    high = midpoint - 1
            if best == 0:
                raise ValueError(
                    "A single character exceeds the configured token split limit"
                )
            pieces.append(remainder[:best])
            cursor += best
        return pieces
