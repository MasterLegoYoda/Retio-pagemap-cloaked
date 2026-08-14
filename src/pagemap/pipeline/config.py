"""Configuration resolution for the pipeline layer.

Reads CLI flags (set in :mod:`pagemap.cli` and the server's
``argparse``), environment variables, and defaults, and returns a
:class:`PipelineConfig` the rest of the server consumes.

Resolution rule, per field, is **CLI > env > default**.

Environment variables:

* ``PAGEMAP_RETRIEVER`` — ``"cloak"`` (default) or ``"fetch"``.
* ``PAGEMAP_EXTRACTOR`` — ``"retio"`` (default), ``"pulpie"``, or
  ``"markdown"``.
* ``PAGEMAP_FAST_BACKEND`` — ``"auto"`` (default), ``"curl_cffi"``,
  ``"httpx"``, or ``"urllib"``.  (Moved from
  ``pagemap.web_fetch``.)
* ``PAGEMAP_SEARCH_PROVIDER`` — default ``"duckduckgo"``.

The full picture of what runs is what ``retio-pagemap --retriever
cloak --extractor retio`` would print: cloak (CloakBrowser) +
retio (PageMap).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_VALID_RETRIEVERS = ("cloak", "fetch", "auto")
_VALID_EXTRACTORS = ("retio", "pulpie", "markdown", "auto")
_VALID_HTTP_BACKENDS = ("auto", "curl_cffi", "httpx", "urllib")
_VALID_SEARCH_PROVIDERS = (
    "auto",
    "duckduckgo",
    "brave",
    "bing",
    "google",
    "searxng",
    "exa",
    "tavily",
    "firecrawl",
)
_VALID_FETCH_MODES = ("browser", "fast")


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Resolved pipeline configuration.

    Attributes:
        retriever_name: ``"cloak"`` or ``"fetch"``.
        extractor_name: ``"retio"``, ``"pulpie"``, or ``"markdown"``.
        http_backend_name: ``"auto"`` (default) or a concrete backend.
        search_provider_name: ``"auto"`` (default) or a concrete provider.
        fetch_mode: ``"browser"`` or ``"fast"``.  ``"fast"`` is a
            legacy alias for ``retriever_name="fetch"`` kept for
            backward compatibility with the
            ``web_fetch(mode="fast", …)`` tool argument.
        extras: Free-form extras (proxy, GeoIP, humanize, etc.).
            Reserved for future use — the PageMap core reads
            Cloak-specific env vars directly today.
    """

    retriever_name: str = "cloak"
    extractor_name: str = "retio"
    http_backend_name: str = "auto"
    search_provider_name: str = "auto"
    fetch_mode: str = "browser"
    extras: dict = field(default_factory=dict)


def _env_first(*names: str) -> str | None:
    """Return the first non-empty env value among ``names``."""
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return None


def _normalize_choice(value: str | None, valid: tuple[str, ...]) -> str:
    """Lowercase ``value``; raise :class:`ValueError` if it isn't in ``valid``."""
    if value is None:
        return valid[0]
    v = value.strip().lower()
    if v not in valid:
        raise ValueError(f"Invalid choice {value!r}. Valid options: {', '.join(valid)}.")
    return v


def _resolve_cli(*, retriever: str | None, extractor: str | None) -> dict[str, str]:
    """Apply CLI overrides (already parsed by argparse)."""
    out: dict[str, str] = {}
    if retriever:
        out["retriever_name"] = _normalize_choice(retriever, _VALID_RETRIEVERS)
    if extractor:
        out["extractor_name"] = _normalize_choice(extractor, _VALID_EXTRACTORS)
    return out


def _resolve_env() -> dict[str, str]:
    """Read configuration from environment variables."""
    out: dict[str, str] = {}

    r = _env_first("PAGEMAP_RETRIEVER")
    if r:
        out["retriever_name"] = _normalize_choice(r, _VALID_RETRIEVERS)

    e = _env_first("PAGEMAP_EXTRACTOR")
    if e:
        out["extractor_name"] = _normalize_choice(e, _VALID_EXTRACTORS)

    b = _env_first("PAGEMAP_FAST_BACKEND")
    if b:
        out["http_backend_name"] = _normalize_choice(b, _VALID_HTTP_BACKENDS)

    p = _env_first("PAGEMAP_SEARCH_PROVIDER", "PAGEMAP_DEFAULT_SEARCH_PROVIDER")
    if p:
        out["search_provider_name"] = _normalize_choice(p, _VALID_SEARCH_PROVIDERS)

    m = _env_first("PAGEMAP_FETCH_MODE")
    if m:
        out["fetch_mode"] = _normalize_choice(m, _VALID_FETCH_MODES)

    return out


def resolve_config(
    *,
    cli_retriever: str | None = None,
    cli_extractor: str | None = None,
) -> PipelineConfig:
    """Resolve the pipeline configuration from CLI, env, and defaults.

    Args:
        cli_retriever: Value of the ``--retriever`` CLI flag, if any.
        cli_extractor: Value of the ``--extractor`` CLI flag, if any.

    Returns:
        A :class:`PipelineConfig` with the final resolved values.
    """
    merged: dict[str, str] = {}
    merged.update(_resolve_env())
    merged.update(_resolve_cli(retriever=cli_retriever, extractor=cli_extractor))

    # Defaults.
    retriever = merged.get("retriever_name", "cloak")
    extractor = merged.get("extractor_name", "retio")
    http_backend = merged.get("http_backend_name", "auto")
    search_provider = merged.get("search_provider_name", "auto")
    fetch_mode = merged.get("fetch_mode", "browser")

    # `auto` -> concrete default.
    if retriever == "auto":
        retriever = "cloak"
    if extractor == "auto":
        extractor = "retio"
    if search_provider == "auto":
        search_provider = "duckduckgo"

    # Sanity check: any registered retriever / extractor the user
    # named must exist in the registry, else they almost certainly
    # misspelled it.  We also probe ``is_available()`` so that an
    # optional-dep extractor (e.g. pulpie without the pulpie
    # package) is rejected with a clear install hint.
    from .extractor import get_extractor, list_extractors
    from .retriever import list_retrievers

    if retriever not in list_retrievers():
        # `auto` already collapsed, so this is a real typo.
        raise ValueError(
            f"Unknown retriever '{retriever}'. Available: {', '.join(list_retrievers())}."
        )
    if extractor not in list_extractors():
        # The extractor might be missing because of a missing
        # optional dep (e.g. pulpie).  Detect that case and raise a
        # friendly error.
        if extractor == "pulpie":
            raise ValueError(
                "Extractor 'pulpie' is not registered. Install the optional "
                "dependency with `pip install 'retio-pagemap[pulpie]'`."
            )
        raise ValueError(
            f"Unknown extractor '{extractor}'. Available: {', '.join(list_extractors())}."
        )

    # Probe availability so the server fails fast at startup with
    # a clear error, not a cryptic 500 mid-tool-call.
    try:
        if not get_extractor(extractor).is_available():
            if extractor == "pulpie":
                raise ValueError(
                    "Extractor 'pulpie' is not available. Install the optional "
                    "dependency with `pip install 'retio-pagemap[pulpie]'`."
                )
            raise ValueError(
                f"Extractor '{extractor}' is registered but reports itself as unavailable."
            )
    except ValueError:
        raise
    except Exception as exc:
        # ``get_extractor`` raises ExtractorError when unavailable; map
        # back to a friendly ValueError so the config layer's contract
        # is consistent.
        if extractor == "pulpie":
            raise ValueError(
                "Extractor 'pulpie' is not available. Install the optional "
                "dependency with `pip install 'retio-pagemap[pulpie]'`."
            ) from exc
        raise ValueError(
            f"Extractor '{extractor}' is not available: {exc}"
        ) from exc

    return PipelineConfig(
        retriever_name=retriever,
        extractor_name=extractor,
        http_backend_name=http_backend,
        search_provider_name=search_provider,
        fetch_mode=fetch_mode,
        extras={},
    )


__all__ = [
    "PipelineConfig",
    "resolve_config",
]
