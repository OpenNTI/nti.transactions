#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

DEFAULT_LONG_RUNNING_COMMIT_IN_SECS = 6
from perfmetrics import Metric
from zope import interface

###
# Monkey-patches
###

# By default, it wants to create a different logger
# for each and every thread or greenlet. We go through
# lots of greenlets, so that's lots of loggers
from transaction import _transaction
# pylint:disable-next=protected-access
_transaction._LOGGER = __import__('logging').getLogger('txn.GLOBAL')

# Introduce a 'nti_abort' function that wraps the raw abort as a metric.
raw_abort = _transaction.Transaction.abort
raw_abort = getattr(raw_abort, 'im_func', raw_abort) # Py2
_transaction.Transaction.nti_abort = Metric('transaction.abort', rate=0.1)(raw_abort)
del raw_abort

# Ditto for commit
raw_commit = _transaction.Transaction.commit
raw_commit = getattr(raw_commit, 'im_func', raw_commit) # Py2
_transaction.Transaction.nti_commit = Metric('transaction.commit', rate=0.1)(raw_commit)
del raw_commit

from .interfaces import IExtendedTransaction
interface.alsoProvides(_transaction.Transaction, IExtendedTransaction)
