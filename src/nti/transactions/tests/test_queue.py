#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import is_
from hamcrest import has_length
from hamcrest import assert_that

import transaction
import six

try:
    from gevent import queue as gevent_queue
except ImportError:
    if six.PY2:
        from Queue import Full
        from Queue import Queue
    else:
        from queue import Full
        from queue import Queue
else: # pragma: no cover
    Full = gevent_queue.Full
    Queue = gevent_queue.Queue

from ..queue import put_nowait

from nti.testing.base import AbstractTestBase

class PutQueueTest(AbstractTestBase):

    def test_put_succeeds(self):
        queue = Queue() # unbounded
        transaction.begin()

        put_nowait(queue, self)
        # still empty
        assert_that(queue.qsize(), is_(0))

        transaction.commit()

        assert_that(queue.get(block=False), is_(self))

    def test_put_transaction_abort(self):
        queue = Queue()
        transaction.begin()
        put_nowait(queue, 'aborted')
        transaction.abort()

        transaction.begin()
        put_nowait(queue, 'committed')
        transaction.commit()

        assert_that(queue.qsize(), is_(1))
        assert_that(queue.get(block=False), is_('committed'))

    def test_put_transaction_savepoint(self):
        queue = Queue()
        transaction.begin()
        put_nowait(queue, 'presavepoint')
        # we can get a non-optimistic savepoint
        savepoint = transaction.savepoint(optimistic=False)
        assert_that(savepoint._savepoints, has_length(1))
        repr(savepoint._savepoints) # cover
        put_nowait(queue, 'aftersavepoint')

        # If we rollback the savepoint now, what we just
        # did will be lost, but the original work
        # will still happen
        savepoint.rollback()
        transaction.commit()

        assert_that(queue.qsize(), is_(1))
        assert_that(queue.get(block=False), is_('presavepoint'))

    def test_put_multiple_correct_order(self):
        # Early builds had a bug where the sort order of the datamanagers
        # was non-deterministic since it was based on object id, and that's not
        # guaranteed to be atomically increasing. It takes a high iteration count to
        # demonstrate this, though
        queue = Queue()

        for _ in range(10000):
            transaction.begin()

            put_nowait(queue, 'a')
            put_nowait(queue, 'b')

            transaction.commit()

            assert_that(queue.get(block=False), is_('a'))
            assert_that(queue.get(block=False), is_('b'))

    def test_put_failure(self):
        queue = Queue(1) # unbounded
        queue.put(object())
        assert_that(queue.qsize(), is_(1))

        transaction.begin()

        put_nowait(queue, self)
        # still size 1
        assert_that(queue.qsize(), is_(1))
        with self.assertRaises(Full) as cm:
            transaction.commit()


        assert_that(cm.exception, is_(Full))
        assert_that(queue.get(block=False), is_(object))
