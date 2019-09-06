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

logger = __import__('logging').getLogger(__name__)

import sys
import time
try:
    from sys import exc_clear
except ImportError: # pragma: no cover
    def exc_clear():
        "Does nothing"
        # Python 3 guarantees this natively.

import six
from perfmetrics import Metric

from zope import interface
from zope.exceptions.exceptionformatter import format_exception
from zope.exceptions.exceptionformatter import print_exception

TRACE = 5 # from ZODB.loglevels.
from .interfaces import CommitFailedError
from .interfaces import AbortFailedError
from .interfaces import ForeignTransactionError
from .interfaces import TransactionLifecycleError

import transaction

from transaction.interfaces import IDataManagerSavepoint
from transaction.interfaces import ISavepointDataManager
from transaction.interfaces import AlreadyInTransaction
from transaction.interfaces import NoTransaction

try:
    from gevent import sleep as _sleep
except ImportError:
    from time import sleep as _sleep

try:
    from queue import Full as QFull
except ImportError:
    # Py2
    # The gevent.queue.Full class is just an alias
    # for the stdlib class, on both Py2 and Py3
    from Queue import Full as QFull


from dm.transaction.aborthook import add_abort_hooks
add_abort_hooks = add_abort_hooks  # pylint

from nti.transactions import DEFAULT_LONG_RUNNING_COMMIT_IN_SECS

__all__ = [
    'ObjectDataManager',
    'OrderedNearEndObjectDataManager',
    'TransactionLoop',
    'do',
    'do_near_end',
    'put_nowait',
]

@interface.implementer(ISavepointDataManager, IDataManagerSavepoint)
class ObjectDataManager(object):
    """
    A generic (and therefore relatively expensive)
    :class:`transaction.interfaces.IDataManager` that invokes a
    callable (usually a method of an object) when the transaction
    finishes successfully. The method should not raise exceptions when
    invoked, as they will be caught and ignored (to preserve
    consistency with the rest of the data managers). If there's a
    chance the method could fail, then whatever actions it does take
    should not have side-effects.

    These data managers have no guaranteed relationship to other data
    managers in terms of the order of which they commit, except as
    documented with :meth:`sortKey`.

    Because these data managers execute exactly one operation on a
    complete transaction commit, implementing a savepoint is trivial:
    do nothing when it is rolled back. A savepoint is created to checkpoint
    a transaction and rolled back to reverse actions taken *after* the
    checkpoint. Only data managers that were active (joined) at the
    time the transaction savepoint is created are asked to create
    their own savepoint, and then potentially to roll it back. We do
    no work until the transaction is committed, so we have nothing
    to rollback. Moroever, if a transaction savepoint is activated
    before a manager joins, then that manager is not asked for its own
    savepoint: it is simply aborted and unjoined from the transaction if
    the previous savepoint is rolledback.

    """

    _EMPTY_KWARGS = {}

    def __init__(self, target=None, method_name=None, call=None,
                 vote=None, args=(), kwargs=None):
        """
        Construct a data manager. You must pass either the `target` and `method_name` arguments
        or the `call` argument. (You may always pass the `target` argument, which will
        be made available on this object for the use of :meth:`tpc_vote`. )

        :param target: An object. Optional if `call` is given. If provided, will be used
            to compute the :meth:`sortKey`.
        :param string method_name: The name of the attribute to get from `target`. Optional if `callable`
            is given.
        :param callable call: A callable object. Ignored if `target` *and* `method_name` are given.
        :param callable vote: If given, then a callable that will be called during the voting phase.
            It should raise an exception if the transaction will fail.
        :param args: A sequence of arguments to pass to the callable object. Optional.
        :param kwargs: A dictionary of arguments to pass to the callable object. Optional.
        """
        self.target = target
        if method_name:
            self.callable = getattr(target, method_name)
        else:
            self.callable = call

        assert self.callable is not None

        self.args = args
        self.kwargs = kwargs or self._EMPTY_KWARGS

        self.vote = vote

        # Use the default thread transaction manager.
        self.transaction_manager = transaction.manager

    def commit(self, tx):
        pass

    def abort(self, tx):
        pass

    def sortKey(self):
        """
        Return the string value that, when sorted, determines the
        order in which data managers will get to vote and commit at
        the end of a transaction. (See
        :meth:`transaction.interfaces.IDataManager.sortKey`).

        The default implementation of this method uses the ID of
        either the ``target`` object we were initialized with or the ID of
        the actual callable we will call. This has the property of
        ensuring that *all* calls to methods of a particular object
        instance (when ``target`` is given), or calls to a particular callable
        (when ``target`` is not given) will execute in the order in which they were
        added to the transaction.

        .. note:: This relies on an implementation detail of the
            transaction package, which sorts using :meth:`list.sort`,
            which is guaranteed to be stable: thus objects using the
            same key remain in the same relative order. (See
            :meth:`transaction._transaction.Transaction._commitResources`.)

        To execute only calls to a particular method of a particular instance
        in the order they are added to the transaction, but allow other
        methods to execute before or after them, do not provide the ``target``.

        It is not advisable to use the ID of this object (``self``) in
        the implementation of this method, because the ID values are
        not guaranteed to be monotonically increasing and thus
        instances of a particular class that did this would execute in
        "random" order.
        """
        # It's not clearly documented, but this is supposed to be a string
        return str(id(self.target) if self.target is not None else id(self.callable))

    # No subtransaction support.
    def abort_sub(self, tx):
        "Does nothing"

    commit_sub = abort_sub

    def beforeCompletion(self, tx):
        "Does nothing"

    afterCompletion = beforeCompletion

    def tpc_begin(self, tx, subtransaction=False): # pylint:disable=unused-argument
        assert not subtransaction

    def tpc_vote(self, tx): # pylint:disable=unused-argument
        if self.vote:
            self.vote()

    def tpc_finish(self, tx): # pylint:disable=unused-argument
        self.callable(*self.args, **self.kwargs)

    tpc_abort = abort

    def __repr__(self):
        return '<%s.%s at %s for %r>' % (self.__class__.__module__, self.__class__.__name__,
                                         id(self),
                                         self.callable)

    # ISavepointDataManager
    def savepoint(self):
        return self

    # IDatamanagerSavepoint
    def rollback(self):
        # See class comments: we have nothing to rollback
        # from because we take no action until commit
        # anyway.
        pass

class OrderedNearEndObjectDataManager(ObjectDataManager):
    """
    A special extension of :class:`ObjectDataManager` that attempts to execute
    after all other data managers have executed. This is useful when an
    operation relies on the execution of other data managers.

    .. versionadded:: 1.1
    """

    def sortKey(self):
        """
        Sort prepended with z's in an attempt to execute after other data
        managers.
        """
        parent_key = super(OrderedNearEndObjectDataManager, self).sortKey()
        sort_str = str(self.target) if self.target is not None else str(self.callable)
        return 'zzz%s:%s' % (sort_str, parent_key)

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

def do(*args, **kwargs):
    """
    Establishes a IDataManager in the current transaction.
    See :class:`ObjectDataManager` for the possible arguments.
    """
    klass = kwargs.pop('datamanager_class', ObjectDataManager)
    result = klass(*args, **kwargs)
    transaction.get().join(result)
    return result

def do_near_end(*args, **kwargs):
    """
    Establishes a IDataManager in the current transaction that will attempt to
    execute *after* all other DataManagers have had their say.
    See :class:`ObjectDataManager` for the possible arguments.

    .. versionadded:: 1.1
    """
    kwargs['datamanager_class'] = OrderedNearEndObjectDataManager
    return do(*args, **kwargs)

def _do_commit(tx, description, long_commit_duration, perf_counter=time.time):
    exc_info = sys.exc_info()
    try:
        begin = perf_counter()
        tx.nti_commit()
        duration = perf_counter() - begin
        if duration > long_commit_duration:
            # We held (or attempted to hold) locks for a really, really, long time. Why?
            logger.warn("Slow running commit for %s in %ss", description, duration)
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
    handle) and runs its handler in the transaction loop.

    The handler code may doom the transaction, but they must not
    attempt to commit or abort it. A doomed transaction, or one whose
    commit is vetoed by :meth:`should_abort_due_to_no_side_effects`
    or :meth:`should_veto_commit` is never retried.

    .. versionchanged:: 3.0

       When this object is called, the thread-local default or global
       TransactionManager is placed into explicit mode (if it wasn't already).
       The handler callable is forbidden from beginning, aborting
       or committing the transaction.
       Explicit transactions can be faster in ZODB, and are easier to reason about.

       If the application begins, commits or aborts the transaction, it can expect this
       object to raise `transaction.interfaces.NoTransaction`,
       `transaction.interfaces.AlreadyInTransaction`
       or `nti.transactions.interfaces.TransactionLifecycleError`.
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

    #: If not none, this should be a number that will be passed to
    #: time.sleep or gevent.sleep in between retries.
    sleep = None
    attempts = 10
    long_commit_duration = DEFAULT_LONG_RUNNING_COMMIT_IN_SECS  # seconds

    #: The default return value from :meth:`should_abort_due_to_no_side_effects`.
    #: If you are not subclassing, or you do not need access to the arguments
    #: of the called function to make this determination, you may set this
    #: as an instance variable.
    side_effect_free = False

    def __init__(self, handler, retries=None, sleep=None,
                 long_commit_duration=None):
        self.handler = handler
        if retries is not None:
            self.attempts = retries + 1
        if long_commit_duration is not None:
            self.long_commit_duration = long_commit_duration
        if sleep is not None:
            self.sleep = sleep

    def prep_for_retry(self, number, *args, **kwargs):
        """
        Called just after a transaction begins if there will be
        more than one attempt possible. Do any preparation
        needed to cleanup or prepare reattempts, or raise
        :class:`AbortAndReturn` if that's not possible.

        :param int number: How many attempts remain. Will always be
          at least 1.
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
        `_retryable_errors` tuple.
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

        try:
            self.setUp()
            return self.__loop(txm, note, args, kwargs)
        finally:
            txm.explicit = was_explicit
            self.tearDown()

    def __loop(self, txm, note, args, kwargs): # pylint:disable=too-many-branches
        number = self.attempts
        need_retry = self.attempts > 1
        begin = txm.begin
        unused_descr = self._UNUSED_DESCRIPTION
        while number:
            number -= 1
            # Throw away any previous exceptions our loop raised.
            # The TB could be taking lots of memory
            exc_clear()
            tx = begin()
            if note and note is not unused_descr:
                tx.note(note)

            try:
                if need_retry:
                    self.prep_for_retry(number, *args, **kwargs)

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
                    # detects a write).

                    # NOTE: We raise these as an exception instead
                    # of aborting in the loop so that we don't
                    # retry if something goes wrong aborting
                    raise self.AbortAndReturn(result, "side-effect free")

                if tx.isDoomed() or self.should_veto_commit(result, *args, **kwargs):
                    raise self.AbortAndReturn(result, "doomed or vetoed")

                _do_commit(tx, note, self.long_commit_duration)

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
                self.__handle_generic_exception(tx, number)
            except SystemExit:
                self.__handle_exit(tx)


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

    def __handle_generic_exception(self, tx, attempts_remaining, _reraise=six.reraise):
        # The code in the transaction package checks the retryable state
        # BEFORE aborting the current transaction. This matters because
        # aborting the transaction changes the transaction that the manager
        # has to a new one, and thus changes the set of registered resources
        # that participate in _retryable, depending on what synchronizers
        # are registered.
        exc_info = sys.exc_info()
        try:
            retryable = self._retryable(tx, exc_info)
            self._abort_on_exception(exc_info, retryable, attempts_remaining, tx)

            if attempts_remaining <= 0 or not retryable: # AFTER the abort
                _reraise(*exc_info)
        finally:
            exc_info = None

        if self.sleep:
            _sleep(self.sleep)

    def __handle_exit(self, tx, _reraise=six.reraise, _exc_info=sys.exc_info):
        # If we are exiting, or otherwise probably going to
        # exit, do try to abort the transaction. The state of
        # the system is somewhat undefined at this point,
        # though, so don't try to time or log it, just print
        # to stderr on exception. Be sure to reraise the
        # original SystemExit
        exc_info = _exc_info()
        try:
            try:
                tx.abort()
            except: # pylint:disable=bare-except
                if print_exception is not None:
                    print_exception(*_exc_info())

            _reraise(*exc_info)
        finally:
            exc_info = None

###
# Monkey-patches
###

# By default, it wants to create a different logger
# for each and every thread or greenlet. We go through
# lots of greenlets, so that's lots of loggers
from transaction import _transaction
_transaction._LOGGER = __import__('logging').getLogger('txn.GLOBAL')

# Introduce a 'nti_abort' function that wraps the raw abort as a metric.
raw_abort = _transaction.Transaction.abort
if hasattr(raw_abort, 'im_func'):
    # Py2
    raw_abort = raw_abort.im_func
_transaction.Transaction.nti_abort = Metric('transaction.abort', rate=0.1)(raw_abort)
del raw_abort

# Ditto for commit
raw_commit = _transaction.Transaction.commit
if hasattr(raw_commit, 'im_func'):
    # Py2
    raw_commit = raw_commit.im_func
_transaction.Transaction.nti_commit = Metric('transaction.commit', rate=0.1)(raw_commit)
del raw_commit
