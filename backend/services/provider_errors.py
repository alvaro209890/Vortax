import httpx


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderOverloadedError(ProviderError):
    pass


def map_httpx_error(exc: httpx.HTTPError, *, provider_name: str) -> ProviderError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return ProviderAuthenticationError(
                f"{provider_name} recusou a chave/API auth (HTTP {status}).",
                status_code=status,
            )
        if status == 429:
            return ProviderRateLimitError(
                f"{provider_name} aplicou rate limit (HTTP 429). Aguarde e tente novamente.",
                status_code=status,
            )
        if status in (502, 503, 504):
            return ProviderOverloadedError(
                f"{provider_name} esta temporariamente indisponivel (HTTP {status}).",
                status_code=status,
            )
        if status >= 500:
            return ProviderError(
                f"{provider_name} retornou erro interno (HTTP {status}).",
                status_code=status,
            )
        return ProviderError(
            f"{provider_name} rejeitou a requisicao (HTTP {status}).",
            status_code=status,
        )
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(f"Timeout ao chamar {provider_name}.")
    return ProviderError(f"Falha de rede ao chamar {provider_name}.")
