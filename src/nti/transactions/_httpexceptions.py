# -*- coding: utf-8 -*-
"""
Exception classes that represent HTTP-level status.

See :mod:`pyramid.httpexceptions`

"""

class HTTPException(Exception):
    """Placeholder if pyramid is not installed."""

class HTTPBadRequest(HTTPException):
    """Placeholder if pyramid is not installed."""

try:
    from pyramid import httpexceptions
except ImportError: # pragma: no cover
    pass
else:
    HTTPException = httpexceptions.HTTPException
    HTTPBadRequest = httpexceptions.HTTPBadRequest

__all__ = [
    'HTTPException',
    'HTTPBadRequest',
]
