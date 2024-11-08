#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Support for transactionally working with queues.
"""

import transaction

from queue import Full as QFull


from .manager import ObjectDataManager

__all__ = [
    'put_nowait',
]


class _QueuePutDataManager(ObjectDataManager):
    """
    A data manager that checks if the queue is full before putting.
    Overrides :meth:`tpc_vote` for efficiency.
    """

    def __init__(self, queue, method, args=()):
        super().__init__(target=queue, call=method, args=args)
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
