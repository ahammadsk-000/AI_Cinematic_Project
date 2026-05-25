"""Domain exceptions. Services raise these; the API layer maps them to HTTP
status codes in one place (app.api.v1.errors). Keeps services framework-agnostic."""

from __future__ import annotations


class DomainError(Exception):
    """Base for all expected, mappable domain errors."""


class NotFoundError(DomainError):
    """Requested resource does not exist or isn't owned by the caller."""


class ConflictError(DomainError):
    """Resource already exists (e.g. duplicate email)."""


class AuthError(DomainError):
    """Invalid credentials / token."""


class ValidationError(DomainError):
    """Business-rule validation failure (distinct from request schema validation)."""
