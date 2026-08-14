"""Exceptions raised by :mod:`pagemap.pipeline.extractor`."""

from __future__ import annotations

from pagemap.pipeline.retriever.errors import WebFetchError


class ExtractorError(WebFetchError):
    """Base class for extractor failures (preserved from web_fetch)."""


class ExtractionError(ExtractorError):
    """Raised when content extraction from an HTML payload fails."""


class ExtractorNotFound(KeyError):
    """No extractor is registered under the requested name.

    Subclasses :class:`KeyError` so ``except KeyError`` keeps working,
    but is its own class so callers can catch it specifically.
    """

    def __init__(self, name: str, *, available: list[str] | None = None) -> None:
        self.name = name
        self.available = available or []
        super().__init__(name)

    def __str__(self) -> str:  # pragma: no cover — formatting
        if self.available:
            return f"Extractor '{self.name}' is not registered. Available: {', '.join(self.available)}."
        return f"Extractor '{self.name}' is not registered."


class MissingCapability(ExtractorError):
    """The resolved pipeline does not declare a capability the caller needs.

    The error message is written to be readable by an agent — it
    names the missing capability and points at the next action.
    """

    def __init__(
        self,
        *,
        pipeline_name: str,
        extractor_name: str,
        capability: int,  # Capability bit value
        tool: str | None = None,
        hint: str | None = None,
    ) -> None:
        from .capabilities import CAPABILITY_NAMES, capability_description

        cap_int = int(capability)
        name = CAPABILITY_NAMES.get(cap_int, f"bit{cap_int}")
        description = capability_description_for(cap_int) or capability_description(
            _as_capability(cap_int)
        )
        if tool:
            msg = (
                f"{tool} requires the {name.upper()} capability ({description}), "
                f"but pipeline '{pipeline_name}' (extractor '{extractor_name}') "
                f"does not declare it."
            )
        else:
            msg = (
                f"Pipeline '{pipeline_name}' (extractor '{extractor_name}') "
                f"does not declare the {name.upper()} capability."
            )
        if hint:
            msg = f"{msg} {hint}"
        else:
            # Default actionable hint.
            msg = (
                f"{msg} Switch to a pipeline whose extractor declares "
                f"{name.upper()} (e.g. --extractor retio)."
            )
        super().__init__(msg)
        self.pipeline_name = pipeline_name
        self.extractor_name = extractor_name
        self.capability = cap_int


def _as_capability(value: int):
    """Late import to avoid a circular dependency at module load time."""
    from .capabilities import Capability

    return Capability(value)


def capability_description_for(value: int) -> str | None:
    """Return the human-readable description for a capability bit value."""
    from .capabilities import CAPABILITY_DESCRIPTIONS

    return CAPABILITY_DESCRIPTIONS.get(value)


__all__ = [
    "ExtractionError",
    "ExtractorError",
    "ExtractorNotFound",
    "MissingCapability",
]
