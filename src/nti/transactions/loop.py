#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Support for working with the :mod:`transaction` module.

This module imports the :mod:`dm.transaction.aborthook` module and
directly provides the :func:`add_abort_hooks` function; you should
call this if you need such functionality.

"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

from logging import DEBUG
from logging import WARNING
from logging import ERROR
from logging import getLogger

import sys
import time
import random
try:
    from sys import exc_clear
except ImportError: # pragma: no cover
    def exc_clear():
        "Does nothing"
        # Python 3 guarantees this natively.

import six

from perfmetrics import statsd_client as _statsd_client

from zope.exceptions.exceptionformatter import format_exception
from zope.exceptions.exceptionformatter import print_exception
from zope.cachedescriptors.property import Lazy
from zope.event import notify

from .interfaces import CommitFailedError
from .interfaces import AbortFailedError
from .interfaces import ForeignTransactionError
from .interfaces import TransactionLifecycleError

from .interfaces import LoopInvocation
from .interfaces import AfterTransactionBegan
from .interfaces import WillFirstAttempt
from .interfaces import WillRetryAttempt
from .interfaces import WillSleepBetweenAttempts

import transaction

from transaction.interfaces import AlreadyInTransaction
from transaction.interfaces import NoTransaction

from nti.transactions import DEFAULT_LONG_RUNNING_COMMIT_IN_SECS

__all__ = [
    'TransactionLoop',
]

logger = getLogger(__name__)

def _do_commit(tx, long_commit_duration,
               retries, sleep_time,
               _logger=logger,
               _DEBUG=DEBUG,
               _WARNING=WARNING,
               _perf_counter=getattr(time, 'perf_counter', time.time)):
    exc_info = sys.exc_info()
    try:
        begin = _perf_counter()
        tx.nti_commit()
        level = _DEBUG
        duration = _perf_counter() - begin
        if duration > long_commit_duration:
            level = _WARNING
        if _logger.isEnabledFor(level):
            _logger.log(
                level,
                "Committed transaction description=%r, duration=%s, retries=%s, sleep_time=%s",
                tx.description, duration, retries, sleep_time
            )
    except TypeError:
        # Translate this into something meaningful
        exc_info = sys.exc_info()
        six.reraise(CommitFailedError, CommitFailedError(exc_info[1]), exc_info[2])
    except (AssertionError, ValueError):
        # We've seen this when we are recalled during retry handling. The higher level
        # is in the process of throwing a different exception and the transaction is
        # already toast, so this commit would never work, but we haven't lost anything;
        # The sad part is that this assertion error overrides the stack trace for what's currently
        # in progress

        # TODO: Prior to transaction 1.4.0, this was only an
        # AssertionError. 1.4 makes it a ValueError, which is hard to
        # distinguish and might fail retries?
        logger.exception("Failing to commit; should already be an exception in progress")
        if exc_info and exc_info[0]:
            six.reraise(*exc_info)

        raise
    finally:
        del exc_info

class TransactionLoop(object):
    """
    Similar to the transaction attempts mechanism, but less error
    prone and with added logging and hooks.

    This object is callable (passing any arguments along to its
    handler) and runs its handler in the transaction loop.

    The handler code may doom the transaction, but they must not
    attempt to commit or abort it. A doomed transaction, or one whose
    commit is vetoed by :meth:`should_abort_due_to_no_side_effects` or
    :meth:`should_veto_commit` is never retried.

    Aborting or committing the transaction will set these :mod:`perfmetrics`
    timers:

    transaction.commit
        Time taken to commit the transaction. Sampled.
    transaction.abort
        Time taken to abort the transaction. Sampled.

    Running the loop will increment these :mod:`perfmetrics` counters
    (new in 3.1):

    transaction.retry
        The number of retries required in any given loop. Note that
        if the handler raises non-retryable exceptions, this number will
        be inflated.
    transaction.side_effect_free
        How many side-effect free transactions there have been.
    transaction.side_effect_free_violation
        How many side-effect free transactions actually had resource
        managers joined to the transaction, and so potentially aborted
        work that wanted to be committed. (3.1.1)
    transaction.vetoed
        How many transactions were vetoed.
    transaction.doomed
        The number of doomed transactions.
    transaction.successful
        The number of transactions that successfully returned.
    transaction.failed
        The number of transactions that did not successfully return.

    .. important::

       Instances of this class must be thread safe, and running the loop should
       not mutate the state of this object.

    .. versionchanged:: 3.0

       When this object is called, the thread-local default or global
       :class:`transaction.TransactionManager` is placed into explicit
       mode (if it wasn't already). The handler callable is forbidden
       from beginning, aborting or committing the transaction. Explicit
       transactions can be faster in ZODB, and are easier to reason
       about.

       If the application begins, commits or aborts the transaction, it
       can expect this object to raise
       :exc:`transaction.interfaces.NoTransaction`,
       :exc:`transaction.interfaces.AlreadyInTransaction` or
       :exc:`nti.transactions.interfaces.TransactionLifecycleError`.

    .. versionchanged:: 3.1

       zope.event is used to publish events after each transaction begins,
       before a transaction is retried or the first attempt is made,
       and before we sleep between retries. See
       :class:`nti.transaction.interfaces.IAfterTransactionBegan`,
       :class:`nti.transaction.interfaces.IWillFirstAttempt`,
       :class:`nti.transaction.interfaces.IWillRetryAttempt`,
       :class:`nti.transaction.interfaces.IWillSleepBetweenAttempt`.
    """

    class AbortAndReturn(Exception):
        """
        This private exception is raised here to cause us to break out
        of our loop, abort the transaction, and return the result.

        .. versionchanged:: 3.0

           Previously this was called ``AbortException``. Until 4.0,
           that name remains available as a deprecated alias.
        """
        def __init__(self, response, reason):
            Exception.__init__(self)
            self.response = response
            self.reason = reason

    #: Deprecated alias for `AbortAndReturn`
    AbortException = AbortAndReturn

    #: If not None, this is a number that specifies the base amount of time
    #: (in seconds) to wait after a failed transaction attempt before retrying. Each
    #: retry attempt will pick a delay following the binary exponential
    #: backoff algorithm: ``sleep * (random number between 0 and 2^retry-1)``.
    #: (A simple increasing multiplier might work well if there is only one other
    #: transaction that we conflict with, but in cases of multiple conflicts
    #: or even new conflicts, the random backoff should provide higher
    #: overall progress.)
    #: This can be set in a subclass if not passed to the constructor.
    sleep = None

    #: How many total attempts will be made, including the initial. This
    #: can be set in a subclass, if not passed to the constructor.
    attempts = 3

    #: Commits longer than this (seconds) will trigger a warning log message.
    #: This can be set in a subclass if not passed to the constructor.
    long_commit_duration = DEFAULT_LONG_RUNNING_COMMIT_IN_SECS  # seconds

    transaction_sample_rate = 0.2

    #: The default return value from :meth:`should_abort_due_to_no_side_effects`.
    #: If you are not subclassing, or you do not need access to the arguments
    #: of the called function to make this determination, you may set this
    #: as an instance variable.
    side_effect_free = False

    #: If the number of resources joined to a transaction exceeds this,
    #: only a summary will be logged.
    #:
    #: .. versionadded:: 4.1.0
    side_effect_free_resource_report_limit = 5

    #: The log level at which to report violations of side-effect-free transactions
    #: (those that are reported as :meth:`should_abort_due_to_no_side_effects`,
    #: but which nonetheless have resource managers joined). This usually signifies
    #: a programming error, and results in throwing away work.
    #: If this is set to :obj:`logging.ERROR` or higher, an exception will be
    #: raised when this happens; this is useful for testing.
    #: The default value is :obj:`logging.DEBUG`.
    #:
    #: .. versionadded:: 4.1.0
    side_effect_free_log_level = DEBUG

    def __init__(
            self, handler,
            retries=None, # type: int
            sleep=None, # type: float
            long_commit_duration=None, # type: float
    ):
        """
        :keyword float sleep: Sets the :attr:`sleep`.
        :keyword int retries: If given, the number of times a transaction will be
            retried. Note that this is one less than the total number of
            :attr:`attempts`
        """
        self.handler = handler
        if retries is not None:
            self.attempts = retries + 1
        if long_commit_duration is not None:
            self.long_commit_duration = long_commit_duration
        if sleep is not None:
            self.sleep = sleep
            self.random = random.SystemRandom()

    def __repr__(self):
        return '<%s.%s at 0x%x attempts=%s long_commit_duration=%s sleep=%s handler=%r>' % (
            type(self).__module__,
            type(self).__name__,
            id(self),
            self.attempts,
            self.long_commit_duration,
            self.sleep,
            self.handler
        )

    def prep_for_retry(self, attempts_remaining, tx, *args, **kwargs):
        """
        Called just after a transaction begins if there will be
        more than one attempt possible. Do any preparation
        needed to cleanup or prepare reattempts, or raise
        :class:`AbortAndReturn` if that's not possible.

        :param int attempts_remaining: How many attempts remain. Will always be
          at least 1.
        :param tx: The transaction that's just begun.

        .. versionchanged:: 3.1
           Add the *tx* parameter.
        """

    def should_abort_due_to_no_side_effects(self, *args, **kwargs): # pylint:disable=unused-argument
        """
        Called after the handler has run. If the handler should
        have produced no side effects and the transaction can be aborted
        as an optimization, return True.

        This defaults to the value of :attr:`side_effect_free`.
        """
        return self.side_effect_free

    def should_veto_commit(self, result, *args, **kwargs): # pylint:disable=unused-argument
        """
        Called after the handler has run. If the result of the handler
        should abort the transaction, return True.
        """
        return False

    _UNUSED_DESCRIPTION = 'Unknown'

    def describe_transaction(self, *args, **kwargs): # pylint:disable=unused-argument
        """
        Return a note for the transaction.

        This should return a string or None. If it returns a string,
        that value will be used via ``transaction.note()``
        """
        return self._UNUSED_DESCRIPTION

    def run_handler(self, *args, **kwargs):
        """
        Actually execute the callable handler.

        This is called from our ``__call__`` method. Subclasses
        may override to customize how the handler is called.
        """
        return self.handler(*args, **kwargs)

    #: Subclasses can customize this to a sequence of (Type, predicate)
    #: objects. If the transaction machinery doesn't know that an exception
    #: is retried, then we check in this list, checking for to see if it is an instance
    #: and applying the relevant test (which defaults to True)
    _retryable_errors = ()

    def _retryable(self, tx, exc_info):
        """
        Should the given exception info be considered one
        we should retry?

        By default, we consult the transaction manager, along with the
        list of (type, predicate) values we have in this object's
        ``_retryable_errors`` tuple.
        """
        v = exc_info[1]
        retryable = False
        try:
            retryable = tx.isRetryableError(v)
            if retryable:
                return retryable
        except Exception: # pylint:disable=broad-except
            pass
        else:
            # retryable was false
            for error_type, test in self._retryable_errors:
                if isinstance(v, error_type):
                    retryable = True if test is None else test(v)
                    break
            return retryable
        finally:
            del exc_info
            del v

    def _abort_on_exception(self, exc_info, retryable, number, tx):
        e = exc_info[0]
        try:
            tx.nti_abort()
            logger.debug("Transaction aborted; retrying %s/%s; '%s'/%r",
                         retryable, number, e, e)
        except (AttributeError, ValueError):
            try:
                logger.exception("Failed to abort transaction following exception "
                                 "(retrying %s/%s; '%s'/%r). New exception:",
                                 retryable, number, e, e)
            except:  # pylint:disable=I0011,W0702
                pass
            # We've seen RelStorage do this:
            # relstorage.cache:427 in after_poll: AttributeError: 'int' object has no attribute 'split' which looks like
            # an issue with how it stores checkpoints in memcache.
            # We have no idea what state it's in after that, so we should
            # abort.

            # We've seen repoze.sendmail do this:
            # repoze.sendmail.delivery:119 in abort: ValueError "TPC in progress"
            # This appears to happen due to some other component raising an exception
            # after the call to commit has begun, and some exception slips through
            # such that, instead of calling `tpc_abort`, the stack unwinds.
            # The sendmail object appears to have been `tpc_begin`, but not
            # `tpc_vote`. (This may happen if the original exception was a ReadConflictError?)
            # https://github.com/repoze/repoze.sendmail/issues/31 (introduced in 4.2)
            # Again, no idea what state things are in, so abort with prejudice.
            try:
                if format_exception is not None:
                    fmt = format_exception(*exc_info)
                    logger.warning("Failed to abort transaction following exception. Original exception:\n%s",
                                   '\n'.join(fmt))
            except: # pylint:disable=bare-except
                exc_info = sys.exc_info()

            six.reraise(AbortFailedError, AbortFailedError(repr(exc_info)), exc_info[2])
        finally:
            del exc_info
            del e

    @staticmethod
    def setUp():
        """
        Called by `__call__` before making any attempts or beginning
        any transaction.

        When this method is called, it is guaranteed that ``transaction.manager.explicit``
        is true.

        Subclasses may override this method. If they are not a direct subclass
        of this class, they should be sure to call the `super` implementation; it
        is not necessary to call this implementation.

        .. versionadded:: 3.0
        """


    @staticmethod
    def tearDown():
        """
        Called by :meth:`__call__` just before returning, in all cases,
        once ``setUp`` has been called.

        When this method is called, it is guaranteed that ``transaction.manager.explicit``
        is at its original value.

        Subclasses may override this method. If they are not a direct subclass
        of this class, they should be sure to call the `super` implementation; it
        is not necessary to call this implementation.

        If this method raises an exception, the original return value of the handler,
        or its exception, will be lost.

        .. versionadded:: 3.0
        """

    _statsd_client = _statsd_client

    class _StatCollector(object):
        # Encapsulates the calls we make to send stats.
        __slots__ = ('client', 'rate', 'buf')
        def __init__(self, client, rate):
            self.client = client
            self.rate = rate
            # We will always send at least two stats, so we can save some network traffic
            # using a buffer. We shouldn't ever send enough to overflow a UDP packet
            # (based on napkin math)
            self.buf = []

        def __call__(self, name, count=1):
            self.client.incr(name, count=count, buf=self.buf, rate=self.rate)

        def flush(self):
            self.client.sendbuf(self.buf)
            del self.buf

    class _NullStatCollector(object):
        @staticmethod
        def __call__(name, count=1):
            "Does nothing"

        @staticmethod
        def flush():
            "Does nothing"

    _null_stat_collector = _NullStatCollector()

    def __call__(self, *args, **kwargs):
        note = self.describe_transaction(*args, **kwargs)

        # We use the thread-local global/default transaction manager.
        # Accessing it directly is a bit faster than going through the wrapping
        # layer. Applications should not be changing it.
        txm = transaction.manager.manager
        # We always operate in explicit mode. This makes finding
        # errors such as committing or aborting multiple times much easier,
        # and prevents us from having to worry about a mis-match between
        # our local Transaction object and the global state.
        was_explicit = txm.explicit
        txm.explicit = True
        client = self._statsd_client()
        stats = (
            self._StatCollector(client, self.transaction_sample_rate)
            if client
            else self._null_stat_collector
        )

        try:
            self.setUp()
            return self.__loop(txm, note, stats, args, kwargs)
        except Exception:
            stats('transaction.failed')
            stats('transaction.retry', self.attempts - 1)
            raise
        finally:
            txm.explicit = was_explicit
            self.tearDown()
            stats.flush()

    def on_begin_failed(self, exc_info, txm, args, kwargs):
        """
        Called when ``begin()`` raised an error other than
        ``AlreadyInTransaction``, probably due to a bad synchronizer.
        Subclasses may override this method.

        After this is called, the tranasction manager *txm* will be aborted.

        This method must not raise an exception.

        .. versionadded:: 4.0.1
        """

    def __loop(self, txm, note, stats, args, kwargs):
        # pylint:disable=too-many-branches,too-many-statements,too-many-locals
        attempts_remaining = self.attempts
        need_retry = self.attempts > 1
        begin = txm.begin
        unused_descr = self._UNUSED_DESCRIPTION
        sleep_time = 0
        invocation = LoopInvocation(self, self.handler, args, kwargs)
        while attempts_remaining:
            attempts_remaining -= 1
            # Starting at 0 for convenience
            attempt_number = self.attempts - attempts_remaining - 1
            # Throw away any previous exceptions our loop raised.
            # The TB could be taking lots of memory
            exc_clear()
            # Bad synchronizers could cause this to raise.
            # That's not good.
            try:
                tx = begin()
            except AlreadyInTransaction: # pragma: no cover
                raise
            except:
                self.on_begin_failed(sys.exc_info(), txm, args, kwargs)

                try:
                    txm.abort()
                except Exception: # pylint:disable=broad-except
                    logger.exception(
                        "Failure when aborting transaction, after failure to begin transaction. "
                        "This exception will be suppressed in favor of the beginning exception "
                        "on Python 3; on Python 2, the beginning exception will be suppressed "
                        "in favor of this one."
                    )

                raise

            if note and note is not unused_descr:
                tx.note(note)
            notify(AfterTransactionBegan(invocation, tx))

            try:
                if need_retry:
                    self.prep_for_retry(attempts_remaining, tx, *args, **kwargs)

                notify((WillFirstAttempt if not attempt_number else WillRetryAttempt)(
                    invocation, tx, attempt_number
                ))
                result = self.run_handler(*args, **kwargs)

                # If the application called commit() or abort(), this will return None
                # A previous call to begin() to change the transaction would have raised
                # AlreadyInTransaction if the application hadn't committed or aborted
                # the transaction, which it should not of course be doing. If we don't check
                # this, then committing the transaction will raise a ValueError
                # from the TransactionManager: ValueError("Foreign transaction") which
                # happens *after* the transaction object has committed; not good.
                # Raise the error now so we can abort the proper object.
                current_tx = self.__has_current_transaction(txm)
                if current_tx is None:
                    tx = None
                    raise TransactionLifecycleError(
                        "The handler aborted or committed one or many transactions "
                        "and did not begin another one. Handlers must not perform "
                        "transaction lifecycle operations."
                    )
                if tx is not current_tx:
                    # Note that we don't handle the NoTransaction case, because
                    # we have no way of knowing whether the transaction was committed
                    # or aborted. Safer just to require the application not to manage
                    # its own transaction.
                    raise ForeignTransactionError(
                        "Transaction currently in progress is not the one the "
                        "loop began. It must have been committed and a new one started. "
                        "Handlers must not perform transaction lifecycle operations."
                    )

                if self.should_abort_due_to_no_side_effects(*args, **kwargs):
                    # These transactions can safely be aborted and
                    # ignored, reducing contention on commit
                    # locks, if any resources had actually been
                    # joined (ZODB Connection only joins when it
                    # detects a write, but those can later be undone by setting
                    # _p_changed = False; this doesn't un-join the transaction).

                    # NOTE: We raise these as an exception instead
                    # of aborting in the loop so that we don't
                    # retry if something goes wrong aborting
                    stats('transaction.side_effect_free')
                    # Detect if we are potentially throwing away work. The transaction
                    # was nominally side-effect free, but resource managers
                    # joined it, so they probably want to do work.
                    # This uses transaction internals, and we don't do a three-arg
                    # getattr(); we want to break if they change.
                    # The list of joined resource managers may be very long
                    # in some cases and it's not always useful to print
                    # all of them.
                    resources = tx._resources or ()

                    if resources:
                        resources = (
                            '(count=%d)' % len(resources)
                            if len(resources) > self.side_effect_free_resource_report_limit
                            else resources
                        )

                        stats('transaction.side_effect_free_violation')
                        logger.log(
                            self.side_effect_free_log_level,
                            "Transaction %r nominally side-effect free has resource managers %s.",
                            tx, resources
                        )
                        if self.side_effect_free_log_level >= ERROR:
                            # Need to grab a copy of `resources` because this will clear it.
                            if not isinstance(resources, str):
                                resources = repr(resources)
                            self.__abort_transaction_quietly(tx)
                            raise TransactionLifecycleError(
                                "Transaction that was supposed to be side-effect free had "
                                "resource managers %s." % (resources,)
                            )
                    raise self.AbortAndReturn(result, "side-effect free")

                if tx.isDoomed() or self.should_veto_commit(result, *args, **kwargs):
                    stats('transaction.doomed' if tx.isDoomed() else 'transaction.vetoed')
                    raise self.AbortAndReturn(result, "doomed or vetoed")

                _do_commit(
                    tx,
                    self.long_commit_duration,
                    attempt_number,
                    sleep_time,
                )
                stats('transaction.successful')
                if attempt_number:
                    stats('transaction.retry', self.attempts - 1 - attempts_remaining)
                return result
            except ForeignTransactionError:
                # They left a transaction hanging around. If it's
                # still ACTIVE, we need to abort it, and clean up
                # after ourself if that fails, pending
                # https://github.com/zopefoundation/transaction/pull/84
                # This could raise lots of exceptions, including
                # ValueError(foreign transaction). We want to raise the FTE,
                # not an AbortFailedError.

                # Our current transaction, by definition, has already been
                # successfully committed or aborted. We only need to worry about
                # the new one, which is in an undetermined state.
                self.__abort_current_transaction_quietly(txm)
                raise

            except (
                    # Programming error: The application called
                    # commit() or abort() and then used transaction.get() (not us, we must
                    # never use an unguarded transaction.get()). The application
                    # should not call commit() or abort() and must be
                    # fixed. The good new is there's nothing to abort: by definition,
                    # our current transaction has been moved past.
                    NoTransaction,
                    # Programming error: The application called commit() or abort(),
                    # and we discovered that there was no active transaction.
                    # The good news is there's nothing to abort, as in the above.
                    TransactionLifecycleError
            ):
                raise
            except (
                    # Programming error: the application called begin() again.
                    # This should be fixed.
                    # The current transaction could still be our initial
                    # transaction, or it could be something else if they also had
                    # one of the other errors, so we have up to two transactions to
                    # to abort.
                    AlreadyInTransaction,
            ):
                current_tx = txm.get()
                self.__abort_current_transaction_quietly(txm)
                if current_tx is not tx:
                    self.__abort_transaction_quietly(tx)
                raise
            except self.AbortAndReturn as e:
                tx.nti_abort()
                return e.response
            except Exception: # pylint:disable=broad-except
                sleep_time += self.__handle_generic_exception(tx, attempts_remaining, invocation)
            except SystemExit:
                self.__handle_exit(tx)
                raise # pragma: no cover


    def __abort_current_transaction_quietly(self, txm):
        self.__abort_transaction_quietly(txm)
        # Ensure we're in a clean state
        # even if abort failed.
        txm._txn = None

    @staticmethod
    def __abort_transaction_quietly(tx):
        try:
            tx.abort()
        except Exception: # Ignore. pylint:disable=broad-except
            pass

    @staticmethod
    def __has_current_transaction(txm):
        # Handles an explicit transaction manager raising an exception
        # when it doesn't have a transaction.
        try:
            return txm.get()
        except NoTransaction:
            return None

    def __handle_generic_exception(self, tx, attempts_remaining, invocation,
                                   _reraise=six.reraise, _exc_info=sys.exc_info):
        # The code in the transaction package checks the retryable state
        # BEFORE aborting the current transaction. This matters because
        # aborting the transaction changes the transaction that the manager
        # has to a new one, and thus changes the set of registered resources
        # that participate in _retryable, depending on what synchronizers
        # are registered.
        exc_info = _exc_info()
        try:
            retryable = self._retryable(tx, exc_info)
            self._abort_on_exception(exc_info, retryable, attempts_remaining, tx)

            if attempts_remaining <= 0 or not retryable:
                _reraise(*exc_info)
        finally:
            exc_info = None

        if self.sleep:
            attempt_num = self.attempts - attempts_remaining # starting at 1
            backoff = self.random.randint(0, 2 ** attempt_num - 1)
            sleep_time = self.sleep * backoff
            event = WillSleepBetweenAttempts(invocation, sleep_time)
            notify(event)
            sleep_time = event.sleep_time
            self._sleep(sleep_time) # pylint:disable=too-many-function-args
        else:
            sleep_time = 0
        return sleep_time


    def __handle_exit(self, tx,
                      _reraise=six.reraise, _exc_info=sys.exc_info, _print_exc=print_exception):
        # If we are exiting, or otherwise probably going to
        # exit, do try to abort the transaction. The state of
        # the system is somewhat undefined at this point,
        # though, so don't try to time or log it, just print
        # to stderr on exception. Be sure to reraise the
        # original SystemExit.
        exc_info = _exc_info()
        try:
            try:
                tx.abort()
            except: # pylint:disable=bare-except
                _print_exc(*_exc_info())

            _reraise(*exc_info)
        finally:
            exc_info = None

    @Lazy
    def _sleep(self):
        # Delay accessing the sleep function until it's used in case
        # it gets monkey patched (e.g., gevent)
        return time.sleep
