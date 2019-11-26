#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Support for transactionally working with queues.
"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import transaction

try:
    from queue import Full as QFull
except ImportError: # pragma: no cover
    # Py2
    # The gevent.queue.Full class is just an alias
    # for the stdlib class, on both Py2 and Py3
    from Queue import Full as QFull

from nti.transactions.manager import ObjectDataManager

__all__ = [
    'put_nowait',
]


class _QueuePutDataManager(ObjectDataManager):
    """
    A data manager that checks if the queue is full before putting.
    Overrides :meth:`tpc_vote` for efficiency.
    """

    def __init__(self, queue, method, args=()):
        super(_QueuePutDataManager, self).__init__(target=queue, call=method, args=args)
        # NOTE: See the `sortKey` method. The use of the queue as the target
        # is critical to ensure that the FIFO property holds when multiple objects
        # are added to a queue during a transaction

    def tpc_vote(self, tx):
        if self.target.full():
            # TODO: Should this be a transient exception?
            # So retry logic kicks in?
            raise QFull()

def put_nowait(queue, obj):
    """
    Transactionally puts `obj` in `queue`. The `obj` will only be visible
    in the queue after the current transaction successfully commits.
    If the queue cannot accept the object because it is full, the transaction
    will be aborted.

    See :class:`gevent.queue.Queue` and :class:`Queue.Full` and :mod:`gevent.queue`.
    """
    transaction.get().join(
        _QueuePutDataManager(queue,
                             queue.put_nowait,
                             args=(obj,)))
