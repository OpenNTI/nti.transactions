# -*- coding: utf-8 -*-
"""
Constants to use for logging levels. See :mod:`ZODB.loglevels`.

"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


try:
    from ZODB.loglevels import TRACE
except ImportError: # pragma: no cover
    TRACE = 5

__all__ = [
    'TRACE',
]
