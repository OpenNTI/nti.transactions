#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""


.. $Id$
"""

from __future__ import print_function, absolute_import, division

#disable: accessing protected members, too many methods
#pylint: disable=W0212,R0904

import unittest

from hamcrest import assert_that
from hamcrest import is_
from hamcrest import calling
from hamcrest import raises
from hamcrest import contains

import fudge

from ..interfaces import CommitFailedError
from ..interfaces import AbortFailedError

from ..transactions import do
from ..transactions import do_near_end
from ..transactions import _do_commit
from ..transactions import TransactionLoop

import transaction
from transaction.interfaces import TransientError


class TestCommit(unittest.TestCase):
    class RaisingCommit(object):
        def __init__(self, t=Exception):
            self.t = t

        def commit(self):
            if self.t:
                raise self.t

    def test_commit_raises_type_error_raises_commit_failed(self):
        assert_that(calling(_do_commit).with_args(self.RaisingCommit(TypeError),
                                                  '', 0),
                    raises(CommitFailedError))

    def test_commit_raises_type_error_raises_commit_failed_good_message(self):
        assert_that(calling(_do_commit).with_args(
            self.RaisingCommit(TypeError("A custom message")),
            '', 0),
                    raises(CommitFailedError, "A custom message"))


    @fudge.patch('nti.transactions.transactions.logger.exception')
    def test_commit_raises_assertion_error(self, fake_logger):
        fake_logger.expects_call()

        assert_that(calling(_do_commit).with_args(self.RaisingCommit(AssertionError),
                                                  '', 0),
                    raises(AssertionError))

    @fudge.patch('nti.transactions.transactions.logger.exception')
    def test_commit_raises_value_error(self, fake_logger):
        fake_logger.expects_call()

        assert_that(calling(_do_commit).with_args(self.RaisingCommit(ValueError),
                                                  '', 0),
                    raises(ValueError))

    @fudge.patch('nti.transactions.transactions.logger.exception')
    def test_commit_raises_custom_error(self, fake_logger):
        fake_logger.expects_call()

        class MyException(Exception):
            pass

        try:
            raise MyException()
        except MyException:
            assert_that(calling(_do_commit).with_args(self.RaisingCommit(ValueError),
                                                      '', 0),
                        raises(MyException))

    @fudge.patch('nti.transactions.transactions.logger.warn')
    def test_commit_clean_but_long(self, fake_logger):
        fake_logger.expects_call()
        _do_commit(self.RaisingCommit(None), '', 0)

class TestLoop(unittest.TestCase):

    def test_trivial(self):
        result = TransactionLoop(lambda a: a, retries=1, long_commit_duration=1, sleep=1)(1)
        assert_that(result, is_(1))

    def test_retriable(self, loop_class=TransactionLoop, exc_type=TransientError):

        calls = []
        def handler():
            if not calls:
                calls.append(1)
                raise exc_type()
            return "hi"

        loop = loop_class(handler)
        result = loop()
        assert_that(result, is_("hi"))
        assert_that(calls, is_([1]))

    def test_custom_retriable(self):
        class Loop(TransactionLoop):
            _retryable_errors = ((Exception, None),)

        self.test_retriable(Loop, AssertionError)

    def test_retriable_gives_up(self):
        def handler():
            raise TransientError()
        loop = TransactionLoop(handler, sleep=0.01, retries=1)
        assert_that(calling(loop), raises(TransientError))

    @fudge.patch('transaction.begin', 'transaction.abort')
    def test_note(self, fake_begin, fake_abort):
        (fake_begin.expects_call()
         .returns_fake()
         .expects('note').with_args("Hi")
         .provides("isDoomed").returns(True))
        fake_abort.expects_call()

        class Loop(TransactionLoop):
            def describe_transaction(self):
                return "Hi"

            def _TransactionLoop__free(self, tx):
                pass

        result = Loop(lambda: 42)()
        assert_that(result, is_(42))


    @fudge.patch('transaction.begin', 'transaction.abort')
    def test_abort_no_side_effect(self, fake_begin, fake_abort):
        fake_begin.expects_call().returns_fake()
        fake_abort.expects_call()

        class Loop(TransactionLoop):
            side_effect_free = True

            def _TransactionLoop__free(self, tx):
                pass

        result = Loop(lambda: 42)()
        assert_that(result, is_(42))

    @fudge.patch('transaction.abort')
    def test_abort_doomed(self, fake_abort):
        fake_abort.expects_call()

        class Loop(TransactionLoop):

            def _TransactionLoop__free(self, tx):
                pass

        def handler():
            transaction.get().doom()
            return 42

        result = Loop(handler)()
        assert_that(result, is_(42))


    @fudge.patch('transaction.abort')
    def test_abort_veto(self, fake_abort):
        fake_abort.expects_call()

        class Loop(TransactionLoop):
            def should_veto_commit(self, result):
                assert_that(result, is_(42))
                return True

            def _TransactionLoop__free(self, tx):
                pass

        result = Loop(lambda: 42)()
        assert_that(result, is_(42))

    @fudge.patch('transaction.begin', 'transaction.abort',
                 'nti.transactions.transactions.print_exception')
    def test_abort_systemexit(self, fake_begin, fake_abort, fake_print):
        from zope.testing.loghandler import Handler

        fake_begin.expects_call().returns_fake()
        fake_abort.expects_call().raises(ValueError)
        fake_print.is_callable()

        class Loop(TransactionLoop):

            def _TransactionLoop__free(self, tx):
                pass

        def handler():
            raise SystemExit()

        loop = Loop(handler)
        try:
            loop()
            self.fail("Should raise SystemExit")
        except SystemExit:
            pass

    @fudge.patch('transaction.begin', 'transaction.abort',
                 'nti.transactions.transactions.logger.exception',
                 'nti.transactions.transactions.logger.warning')
    def test_abort_exception_raises(self, fake_begin, fake_abort,
                                    fake_logger, fake_format):
        fake_begin.expects_call().returns_fake()
        # aborting itself raises a ValueError, which
        # gets transformed
        fake_abort.expects_call().raises(ValueError)

        # Likewise for the things we try to do to log it
        fake_logger.expects_call().raises(ValueError)
        fake_format.expects_call().raises(ValueError)

        class Loop(TransactionLoop):

            def _TransactionLoop__free(self, tx):
                pass

        def handler():
            raise Exception()

        loop = Loop(handler)
        assert_that(calling(loop), raises(AbortFailedError))

class TestDataManagers(unittest.TestCase):

    def test_data_manager_sorting(self):
        results = []
        def test_call(x):
            results.append(x)

        # The managers will execute in order added (since identical),
        # except for the one that requests to go last.
        manager1 = do(call=test_call, args=(0,))
        manager2 = do(call=test_call, args=(1,))
        manager_post = do_near_end(call=test_call, args=(10,))
        manager3 = do(call=test_call, args=(2,))
        transaction.commit()
        assert_that(results, contains(0, 1, 2, 10))
