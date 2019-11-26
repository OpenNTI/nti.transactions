# -*- coding: utf-8 -*-
"""
Exception classes that represent HTTP-level status.

See :mod:`pyramid.httpexceptions`

"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

class HTTPException(Exception):
    "Placeholder if pyramid is not installed."
class HTTPBadRequest(HTTPException):
    "Placeholder if pyramid is not installed."

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
