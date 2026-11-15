"""Classifier providers. Each module exposes `create(model: str | None) -> Classifier`.

Adding one (e.g. a Google provider) = a module here + an entry in PROVIDERS. Vendor SDKs
are imported only inside these modules, and only when that provider is selected.
"""

from __future__ import annotations

import importlib

from eventalpha.classification.base import Classifier

PROVIDERS: dict[str, str] = {
    "typesafe": "eventalpha.classification.providers.typesafe",
}


def _module(provider: str):
    try:
        return importlib.import_module(PROVIDERS[provider])
    except KeyError:
        raise ValueError(f"unknown classifier provider {provider!r}; known: {sorted(PROVIDERS)}") from None


def create_classifier(provider: str, model: str | None = None) -> Classifier:
    return _module(provider).create(model)


def resolve_model_id(provider: str, model: str | None = None) -> str:
    """The id scores are stored under ("<provider>:<model>"), without creating a client."""
    return f"{provider}:{model or _module(provider).DEFAULT_MODEL}"
