#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Legacy module containing re-exports of other objects.
"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

# BWC imports
# For 4.0 makke this produce a deprecation warning. For 5.0
# remove this.
from dm.transaction.aborthook import add_abort_hooks
from nti.transactions.loop import TransactionLoop
from nti.transactions.manager import ObjectDataManager
from nti.transactions.manager import OrderedNearEndObjectDataManager
from nti.transactions.manager import do
from nti.transactions.manager import do_near_end
from nti.transactions.queue import put_nowait

__all__ = [
    'ObjectDataManager',
    'OrderedNearEndObjectDataManager',
    'TransactionLoop',
    'do',
    'do_near_end',
    'put_nowait',
    'add_abort_hooks',
]
