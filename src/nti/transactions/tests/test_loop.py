#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, division

# pylint:disable=too-many-public-methods

import logging
import sys
import unittest

import zope.event

from hamcrest import assert_that
from hamcrest import is_
from hamcrest import is_not as does_not
from hamcrest import calling
from hamcrest import raises
from hamcrest import has_property
from hamcrest import none
from hamcrest import has_items
from hamcrest import greater_than_or_equal_to
from hamcrest import contains
from hamcrest import contains_string

import fudge

from nti.testing.matchers import is_true
from nti.testing.matchers import is_false
from nti.testing.matchers import has_length

from ..interfaces import CommitFailedError
from ..interfaces import AbortFailedError
from ..interfaces import ForeignTransactionError
from ..interfaces import TransactionLifecycleError
from ..interfaces import AfterTransactionBegan
from ..interfaces import WillFirstAttempt
from ..interfaces import WillRetryAttempt
from ..interfaces import WillSleepBetweenAttempts

from ..loop import _do_commit
from ..loop import TransactionLoop

import transaction
from transaction.interfaces import TransientError
from transaction.interfaces import NoTransaction
from transaction.interfaces import AlreadyInTransaction

from perfmetrics.testing import FakeStatsDClient
from perfmetrics.testing.matchers import is_counter
from perfmetrics import statsd_client_stack

from ZODB import DB
from ZODB.DemoStorage import DemoStorage
from ZODB.POSException import StorageError


if str is bytes:
    # The Python 2 version of hamcrest has a bug
    # where it assumes the mismatch_description is
    # not None in one branch.
    from hamcrest.core.core.allof import AllOf
    from hamcrest.core.string_description import StringDescription
    old_func = AllOf.matches.__func__
    def matches(self, item, mismatch_description=None):
        if mismatch_description is None:
            mismatch_description = StringDescription()
        return old_func(self, item, mismatch_description)

    AllOf.matches = matches


class TestCommit(unittest.TestCase):
    class Transaction(object):
        description = u''
        def __init__(self, t=None):
            self.t = t

        def nti_commit(self):
            if self.t:
                raise self.t # (Python2, old pylint)  pylint:disable=raising-bad-type

    def RaisingCommit(self, t=Exception):
        return self.Transaction(t)

    def test_commit_raises_type_error_raises_commit_failed(self):
        assert_that(calling(_do_commit)
                    .with_args(
                        self.RaisingCommit(TypeError),
                        '', 0, 0, 0
                    ),
                    raises(CommitFailedError))

    def test_commit_raises_type_error_raises_commit_failed_good_message(self):
        assert_that(calling(_do_commit)
                    .with_args(
                        self.RaisingCommit(TypeError("A custom message")),
                        '', 0, 0, 0,
                    ),
                    raises(CommitFailedError, "A custom message"))


    @fudge.patch('nti.transactions.loop.logger.exception')
    def test_commit_raises_assertion_error(self, fake_logger):
        fake_logger.expects_call()

        assert_that(calling(_do_commit)
                    .with_args(
                        self.RaisingCommit(AssertionError), '', 0, 0, 0
                    ),
                    raises(AssertionError))

    @fudge.patch('nti.transactions.loop.logger.exception')
    def test_commit_raises_value_error(self, fake_logger):
        fake_logger.expects_call()

        assert_that(calling(_do_commit)
                    .with_args(
                        self.RaisingCommit(ValueError),
                        '', 0, 0, 0,
                    ),
                    raises(ValueError))

    @fudge.patch('nti.transactions.loop.logger.exception')
    def test_commit_raises_custom_error(self, fake_logger):
        fake_logger.expects_call()

        class MyException(Exception):
            pass

        try:
            raise MyException()
        except MyException:
            assert_that(calling(_do_commit)
                        .with_args(
                            self.RaisingCommit(ValueError),
                            '', 0, 0, 0
                        ),
                        raises(MyException))

    @fudge.patch('nti.transactions.loop.logger.log')
    def test_commit_clean_but_long(self, fake_logger):
        fake_logger.expects_call()
        _do_commit(self.RaisingCommit(None), -1, 0, 0)


    @fudge.patch('nti.transactions.loop.logger.isEnabledFor',
                 'nti.transactions.loop.logger.log')
    def test_commit_duration_logging_short(self, fake_is_enabled, fake_log):
        fake_is_enabled.expects_call().returns(True).with_args(logging.DEBUG)
        fake_log.expects_call()
        _do_commit(self.Transaction(), 6, 0, 0)

    @fudge.patch('nti.transactions.loop.logger.isEnabledFor',
                 'nti.transactions.loop.logger.log')
    def test_commit_duration_logging_long(self, fake_is_enabled, fake_log):
        fake_is_enabled.expects_call().returns(True).with_args(logging.WARNING)
        fake_log.expects_call()
        fake_perf_counter = fudge.Fake(
        ).expects_call(
        ).returns(
            0
        ).next_call(
        ).returns(
            10
        )
        _do_commit(self.Transaction(), 6, 0, 0, _perf_counter=fake_perf_counter)


class TrueStatsDClient(FakeStatsDClient):
    # https://github.com/zodb/perfmetrics/issues/23
    def __bool__(self):
        return True
    __nonzero__ = __bool__


class TestLoop(unittest.TestCase):

    def setUp(self):
        try:
            transaction.abort()
        except NoTransaction:
            pass
        transaction.manager.clearSynchs()
        self.statsd_client = TrueStatsDClient()
        self.statsd_client.random = lambda: 0 # Ignore rate, capture all packets
        statsd_client_stack.push(self.statsd_client)
        self.events = []
        zope.event.subscribers.append(self.events.append)

    def tearDown(self):
        statsd_client_stack.pop()
        zope.event.subscribers.remove(self.events.append)
        transaction.manager.clearSynchs()

    @fudge.patch('nti.transactions.loop._do_commit')
    def test_trivial(self, fake_commit):
        class Any(object):
            def __eq__(self, other):
                return True

        loop = TransactionLoop(lambda a: a, retries=1, long_commit_duration=1, sleep=1)
        r = repr(loop)
        assert_that(r, contains_string('sleep=1'))
        assert_that(r, contains_string('long_commit_duration=1'))
        assert_that(r, contains_string('attempts=2'))
        fake_commit.expects_call().with_args(
            Any(), # transaction
            loop.long_commit_duration,
            0, # attempt number / retries
            0 # sleep_time
        )

        result = loop(1)
        assert_that(result, is_(1))
        # May or may not get a transaction.commit stat first, depending on random
        assert_that(self.statsd_client.packets, has_length(greater_than_or_equal_to(1)))
        assert_that(self.statsd_client.observations[-1],
                    is_counter(name='transaction.successful', value=1))

        assert_that(self.events, has_length(2))
        assert_that(self.events, contains(is_(AfterTransactionBegan), is_(WillFirstAttempt)))

    def test_explicit(self):
        assert_that(transaction.manager, has_property('explicit', is_false()))

        def handler():
            assert_that(transaction.manager, has_property('explicit', is_true()))
            return 42

        result = TransactionLoop(handler)()
        assert_that(result, is_(42))

    def test_synchronizer_raises_error_on_begin(self):
        class SynchError(Exception):
            pass

        class Synch(object):
            count = 0
            def newTransaction(self, _txn):
                self.count += 1
                if self.count == 1:
                    raise SynchError


            def afterCompletion(self, _txm):
                pass

            beforeCompletion = afterCompletion


        synch = Synch()
        transaction.manager.registerSynch(synch)

        class HandlerError(Exception):
            pass

        def handler():
            raise HandlerError

        # Doing it the first time fails
        loop = TransactionLoop(handler)
        with self.assertRaises(SynchError):
            loop()

        # Our synch doesn't raise the second time,
        # and we don't get AlreadyInTransaction.
        with self.assertRaises(HandlerError):
            loop()

    def test_zodb_synchronizer_raises_error_on_begin(self):
        # Closely mimic what we see in
        # https://github.com/NextThought/nti.transactions/issues/49,
        # where the storage's ``pollInvalidations`` method
        # raises errors.
        db = DB(DemoStorage())
        # The connection has to be open to register a synch
        conn = db.open()

        def bad_poll_invalidations():
            raise StorageError

        conn._storage.poll_invalidations = bad_poll_invalidations

        # For the fun of it, lets assume that afterCompletion is also broken
        class CompletionError(Exception):
            pass
        def bad_afterCompletion():
            raise CompletionError
        conn._storage.afterCompletion = bad_afterCompletion

        def handler():
            self.fail("Never get here")

        loop = TransactionLoop(handler)

        # Python 2 and Python 3 raise different things
        expected = StorageError if str is not bytes else CompletionError
        for _ in range(2):
            with self.assertRaises(expected):
                loop()

    def test_explicit_begin(self):
        def handler():
            transaction.begin()

        assert_that(calling(TransactionLoop(handler)), raises(AlreadyInTransaction))

    def test_explicit_begin_after_commit(self):
        # We change the current transaction out and then still manage to raise
        # AlreadyInTransaction
        def handler():
            transaction.abort()
            transaction.begin()
            transaction.begin()

        assert_that(calling(TransactionLoop(handler)), raises(AlreadyInTransaction))


    def test_explicit_end(self):
        def handler():
            transaction.abort()

        assert_that(calling(TransactionLoop(handler)), raises(TransactionLifecycleError))

    def test_explicit_foreign(self):
        def handler():
            transaction.abort()
            transaction.begin()

        assert_that(calling(TransactionLoop(handler)), raises(ForeignTransactionError))

    def test_explicit_foreign_abort_fails(self):
        def bad_abort():
            raise Exception("Bad abort")

        def handler():
            transaction.abort()
            tx = transaction.begin()
            tx.abort = tx.nti_abort = bad_abort

        assert_that(calling(TransactionLoop(handler)), raises(ForeignTransactionError))
        assert_that(transaction.manager.manager, has_property('_txn', is_(none())))

    def test_setup_teardown(self):

        class Loop(TransactionLoop):
            setupcalled = teardowncalled = False
            def setUp(self):
                assert_that(transaction.manager, has_property('explicit', is_true()))
                self.setupcalled = True
            def tearDown(self):
                self.teardowncalled = True

        def handler():
            raise Exception

        loop = Loop(handler)
        assert_that(calling(loop), raises(Exception))

        assert_that(loop, has_property('setupcalled', is_true()))
        assert_that(loop, has_property('teardowncalled', is_true()))

    def test_retriable(self, loop_class=TransactionLoop, exc_type=TransientError,
                       raise_count=1, loop_args=(), loop_kwargs=None):

        calls = []
        def handler():
            # exc_info should be clear on entry.
            assert_that(sys.exc_info(), is_((None, None, None)))
            if len(calls) < raise_count:
                calls.append(1)
                raise exc_type(calls)
            return "hi"

        loop = loop_class(handler, *loop_args, **(loop_kwargs or {}))
        result = loop()
        assert_that(result, is_("hi"))
        assert_that(calls, is_([1] * raise_count))
        observations = self.statsd_client.observations
        assert_that(observations,
                    has_items(
                        is_counter(name='transaction.successful', value=1),
                        is_counter(name='transaction.retry', value=raise_count)))
        return loop

    def test_custom_retriable(self):
        class Loop(TransactionLoop):
            _retryable_errors = ((Exception, None),)

        self.test_retriable(Loop, AssertionError)

    def test_retriable_gives_up(self):
        def handler():
            raise TransientError()
        loop = TransactionLoop(handler, sleep=0.01, retries=1)
        assert_that(calling(loop), raises(TransientError))

    def test_non_retryable(self):
        class MyError(Exception):
            pass
        def handler():
            raise MyError()
        loop = TransactionLoop(handler, sleep=0.01, retries=100000000)
        assert_that(calling(loop), raises(MyError))
        observations = self.statsd_client.observations
        assert_that(observations,
                    has_items(
                        is_counter(name='transaction.failed', value=1)))

    def test_isRetryableError_exception(self):
        # If the transaction.isRetryableError() raises, for some reason,
        # we still process our list
        class MyError(object):
            pass
        class Loop(TransactionLoop):
            _retryable_errors = ((MyError, None),)

        loop = Loop(None)
        loop._retryable(None, (None, MyError(), None))

    def test_retryable_backoff(self):
        class NotRandom(object):
            def randint(self, _floor, ceiling):
                return ceiling

        class Loop(TransactionLoop):
            attempts = 10
            def __init__(self, *args, **kwargs):
                TransactionLoop.__init__(self, *args, **kwargs)
                self.times = []
                self.random = NotRandom()
                self._sleep = self.times.append

        # By default, it is not called.
        loop = self.test_retriable(Loop, raise_count=5)
        assert_that(loop, has_property('times', []))

        # Setting a delay calls it
        loop = self.test_retriable(Loop, raise_count=5, loop_kwargs={'sleep': 0.1})
        # The ceiling arguments are 2**attempt - 1, so
        # 1, 3, 7, 15, 31, and sleep times are
        # 0.1, 0.3, 0.7, 1.5, 3,1
        times = [(2 ** x - 1) * 0.1 for x in range(1, 6)]
        assert_that(loop, has_property('times',
                                       times))

        assert_that(self.events, has_length(29))

        assert_that(self.events[-1], is_(WillRetryAttempt))
        assert_that(self.events[-2], is_(AfterTransactionBegan))
        assert_that(self.events[-3], is_(WillSleepBetweenAttempts))
        assert_that(self.events[-3], has_property('sleep_time', 3.1))

    @fudge.patch('transaction._manager.TransactionManager.begin',
                 'transaction._manager.TransactionManager.get')
    def test_note(self, fake_begin, fake_get):
        fake_tx = fudge.Fake()
        (fake_tx
         .expects('note').with_args(u'Hi')
         .expects('nti_abort')
         .provides('isDoomed').returns(True))
        fake_begin.expects_call().returns(fake_tx)
        fake_get.expects_call().returns(fake_tx)
        class Loop(TransactionLoop):
            def describe_transaction(self, *args, **kwargs):
                return u"Hi"

        result = Loop(lambda: 42)()
        assert_that(result, is_(42))


    @fudge.patch('transaction._manager.TransactionManager.begin',
                 'transaction._manager.TransactionManager.get')
    def test_abort_no_side_effect(self, fake_begin, fake_get):
        fake_tx = fudge.Fake()
        fake_tx.expects('nti_abort')
        fake_tx.has_attr(_resources=())

        fake_begin.expects_call().returns(fake_tx)
        fake_get.expects_call().returns(fake_tx)


        class Loop(TransactionLoop):
            side_effect_free = True

        result = Loop(lambda: 42)()
        assert_that(result, is_(42))
        observations = self.statsd_client.observations
        assert_that(observations,
                    has_items(
                        is_counter(name='transaction.side_effect_free', value=1)))
        assert_that(observations,
                    does_not(
                        has_items(
                            is_counter(name='transaction.side_effect_free_violation')
                        )))

    @fudge.test
    def test_abort_no_side_effect_violation(self):
        fake_manager = fudge.Fake().is_a_stub()

        class Loop(TransactionLoop):
            side_effect_free = True

        def handler():
            transaction.get().join(fake_manager)

        loop = Loop(handler)
        loop()
        observations = self.statsd_client.observations
        assert_that(observations,
                    has_items(
                        is_counter(name='transaction.side_effect_free', value=1)))
        assert_that(observations,
                    has_items(
                        is_counter(name='transaction.side_effect_free_violation', value=1)
                    ))

        loop.side_effect_free_log_level = logging.ERROR
        with self.assertRaises(TransactionLifecycleError) as exc:
            loop()

        ex = exc.exception
        assert_that(str(ex),
                    is_("Transaction that was supposed to be side-effect free "
                        "had resource managers [fake:fake_manager]."))

        loop.side_effect_free_resource_report_limit = 0
        with self.assertRaises(TransactionLifecycleError) as exc:
            loop()

        ex = exc.exception
        assert_that(str(ex),
                    is_("Transaction that was supposed to be side-effect free "
                        "had resource managers (count=1)."))


    @fudge.patch('transaction._transaction.Transaction.nti_abort')
    def test_abort_doomed(self, fake_abort):
        fake_abort.expects_call()

        def handler():
            assert_that(transaction.manager.explicit, is_true())
            transaction.get().doom()
            return 42

        result = TransactionLoop(handler)()
        assert_that(result, is_(42))
        observations = self.statsd_client.observations
        assert_that(observations,
                    has_items(
                        is_counter(name='transaction.doomed', value=1)))

    @fudge.patch('transaction._manager.TransactionManager.begin',
                 'transaction._manager.TransactionManager.get')
    def test_abort_veto(self, fake_begin, fake_get):
        fake_tx = fudge.Fake()
        fake_tx.expects('nti_abort')
        fake_tx.provides('isDoomed').returns(False)

        fake_begin.expects_call().returns(fake_tx)
        fake_get.expects_call().returns(fake_tx)

        class Loop(TransactionLoop):
            def should_veto_commit(self, result, *args, **kwargs):
                assert_that(result, is_(42))
                return True

        result = Loop(lambda: 42)()
        assert_that(result, is_(42))
        observations = self.statsd_client.observations
        assert_that(observations,
                    has_items(
                        is_counter(name='transaction.vetoed', value=1)))

    @fudge.patch('transaction._manager.TransactionManager.begin',
                 'sys.stderr')
    def test_abort_systemexit(self, fake_begin, fake_stderr):
        fake_tx = fudge.Fake()
        fake_tx.expects('abort').raises(ValueError)
        fake_tx.provides('isDoomed').returns(False)

        fake_begin.expects_call().returns(fake_tx)
        fake_stderr.provides('write')

        def handler():
            raise SystemExit()

        loop = TransactionLoop(handler)
        try:
            loop()
            self.fail("Should raise SystemExit")
        except SystemExit:
            pass

    @fudge.patch('transaction._manager.TransactionManager.begin',
                 'nti.transactions.loop.logger.exception',
                 'nti.transactions.loop.logger.warning')
    def test_abort_exception_raises(self, fake_begin,
                                    fake_logger, fake_format):
        # begin() returns an object without abort(), which we catch.
        fake_begin.expects_call().returns_fake()

        # Likewise for the things we try to do to log it
        fake_logger.expects_call().raises(ValueError)
        fake_format.expects_call().raises(ValueError)

        def handler():
            raise Exception()
        loop = TransactionLoop(handler)
        assert_that(calling(loop), raises(AbortFailedError))
