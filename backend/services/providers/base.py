"""Shared HTTP boundary for external public-data providers.

The boundary deliberately does not include request parameters, response bodies, or
underlying exception text in its public exceptions. Public-data gateway errors can
contain a prepared URL, and that URL contains the server-only service key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, Mapping, TypeVar
from urllib.parse import urljoin, urlsplit

import requests


RecordT = TypeVar("RecordT")


class ProviderError(RuntimeError):
    """Base class for sanitized provider failures."""


class ProviderConfigurationError(ProviderError):
    """The provider client cannot be configured safely."""


class ProviderTransportError(ProviderError):
    """A network or HTTP failure, without the credential-bearing request URL."""

    def __init__(self, provider: str, *, status_code: int | None = None) -> None:
        self.provider = provider
        self.status_code = status_code
        suffix = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"{provider} request failed{suffix}")


class ProviderResponseError(ProviderError):
    """The provider returned a syntactically valid error response."""

    def __init__(self, provider: str, result_code: str) -> None:
        self.provider = provider
        self.result_code = result_code
        super().__init__(f"{provider} rejected the request (result code {result_code})")


class ProviderPayloadError(ProviderError):
    """The provider payload does not satisfy the documented response contract."""

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        super().__init__(f"{provider} returned an invalid payload: {reason}")


@dataclass(frozen=True, slots=True)
class ProviderResult(Generic[RecordT]):
    """A typed result that intentionally excludes the raw provider payload."""

    provider: str
    endpoint: str
    records: tuple[RecordT, ...]
    reported_total_count: int | None


class JsonProviderClient:
    """Small JSON GET client with bounded retries and sanitized failures."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        session: Any | None = None,
        timeout: tuple[float, float] = (3.05, 10.0),
        max_retries: int = 2,
        backoff_factor: float = 0.25,
        max_retry_delay: float = 2.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed_url = urlsplit(base_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ProviderConfigurationError(
                f"{provider} base URL must be an absolute HTTPS URL"
            )
        if len(timeout) != 2 or any(value <= 0 for value in timeout):
            raise ProviderConfigurationError(
                f"{provider} connect/read timeouts must both be positive"
            )
        if not 0 <= max_retries <= 5:
            raise ProviderConfigurationError(
                f"{provider} max_retries must be between 0 and 5"
            )
        if backoff_factor < 0 or max_retry_delay < 0:
            raise ProviderConfigurationError(
                f"{provider} retry delays cannot be negative"
            )

        self._provider = provider
        self._base_url = base_url.rstrip("/") + "/"
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._max_retry_delay = max_retry_delay
        self._sleeper = sleeper

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={self._base_url!r}, "
            f"timeout={self._timeout!r}, max_retries={self._max_retries})"
        )

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> "JsonProviderClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get_json(self, endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if not endpoint.startswith("/"):
            raise ProviderConfigurationError(
                f"{self._provider} endpoint must start with a slash"
            )

        url = urljoin(self._base_url, endpoint.lstrip("/"))
        if urlsplit(url).scheme != "https":
            raise ProviderConfigurationError(
                f"{self._provider} endpoint must resolve to HTTPS"
            )

        for attempt in range(self._max_retries + 1):
            response: Any | None = None
            try:
                response = self._session.get(
                    url,
                    params=dict(params),
                    timeout=self._timeout,
                )
            except requests.RequestException:
                # Leave the except block before raising so even ``__context__``
                # cannot retain a credential-bearing prepared URL.
                pass
            if response is None:
                if attempt < self._max_retries:
                    self._sleeper(
                        min(
                            self._backoff_factor * (2**attempt),
                            self._max_retry_delay,
                        )
                    )
                    continue
                raise ProviderTransportError(self._provider)

            http_failed = False
            try:
                response.raise_for_status()
            except requests.RequestException:
                http_failed = True
            if http_failed:
                status_code = self._status_code(response)
                if (
                    self._is_retryable_status(status_code)
                    and attempt < self._max_retries
                ):
                    self._sleeper(self._retry_delay(response, attempt))
                    continue
                raise ProviderTransportError(
                    self._provider, status_code=status_code
                )

            json_failed = False
            payload: Any = None
            try:
                payload = response.json()
            except (TypeError, ValueError):
                json_failed = True
            if json_failed:
                raise ProviderPayloadError(self._provider, "response is not JSON")

            if not isinstance(payload, Mapping):
                raise ProviderPayloadError(
                    self._provider, "JSON root is not an object"
                )
            return payload

        # The bounded loop always returns or raises; this keeps type checkers honest.
        raise ProviderTransportError(self._provider)

    @staticmethod
    def _status_code(response: Any) -> int | None:
        value = getattr(response, "status_code", None)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _is_retryable_status(status_code: int | None) -> bool:
        return status_code == 429 or (
            status_code is not None and 500 <= status_code <= 599
        )

    def _retry_delay(self, response: Any, attempt: int) -> float:
        headers = getattr(response, "headers", None)
        retry_after = headers.get("Retry-After") if isinstance(headers, Mapping) else None
        if retry_after is not None:
            try:
                seconds = float(retry_after)
            except (TypeError, ValueError):
                seconds = -1.0
            if seconds >= 0:
                return min(seconds, self._max_retry_delay)

        delay = self._backoff_factor * (2**attempt)
        return min(delay, self._max_retry_delay)
