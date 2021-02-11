#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Interfaces for nti.transactions.

"""

from __future__ import print_function, absolute_import, division

from zope.interface import Interface
from zope.interface import Attribute
from zope.interface import implementer

from transaction.interfaces import TransactionError
from transaction.interfaces import ITransaction

# pylint:disable=no-method-argument,inherit-non-class
# Sigh. The Python 2 version of pylint raises this.
# pylint:disable=too-many-ancestors

class IExtendedTransaction(ITransaction):
    """Extensions to the transaction api."""

    def nti_commit():
        """
        Like ``commit``, but produces a :obj:`perfmetrics.Metric` ``transaction.commit``
        metric.
        """

    def nti_abort():
        """
        Like ``abort``, but produces a :obj:`perfmetrics.Metric`
        ``transaction.abort`` metric.
        """

class CommitFailedError(TransactionError):
    """
    Committing the active transaction failed for an unknown
    and unexpected reason.

    This is raised instead of raising very generic system exceptions such as
    TypeError.
    """

class AbortFailedError(TransactionError):
    """
    Aborting the active transaction failed for an unknown and unexpected
    reason.

    This is raised instead of raising very generic system exceptions
    such as ValueError and AttributeError.
    """

class TransactionLifecycleError(TransactionError):
    """
    Raised when an application commits or aborts a transaction
    while the transaction controller believes it is in control.

    *Applications must not raise this exception.*

    This may have happened many times; we cannot detect that.

    This is a programming error.
    """

class ForeignTransactionError(TransactionLifecycleError):
    """
    Raised when a transaction manager has its transaction changed
    while a controlling transaction loop believes it is in control.

    The handler first aborted or committed the transaction, and then
    began a new one. Possibly many times.

    A kind of `TransactionLifecycleError`. *Applications must not
    raise this exception.*

    This is a programming error.
    """

class ILoopInvocation(Interface):
    """
    Description of why a loop was invoked.
    """
    handler = Attribute("The handler to run.")
    loop = Attribute("The loop doing the running.")
    args = Attribute("The arguments passed to the handler")
    kwargs = Attribute("The keyword arguments passed to the handler.")

class ILoopEvent(Interface):
    """
    Base class for event loop events.

    The *handler_args* and *handler_kwargs* should not
    be mutated in place or assigned to. These are a convenience
    for accessing the attributes of the *invocation* attribute.

    .. versionchanged:: 4.2.0
       Add the *handler_args* and *handler_kwargs*.
    """
    invocation = Attribute("An ILoopInvocation.")
    handler_args = Attribute("The positional arguments for the handler, or ()")
    handler_kwargs = Attribute("The keyword arguments for the handler, or {}")

class IAfterTransactionBegan(ILoopEvent):
    """
    A new transaction has begun.
    """

    tx = Attribute("The transaction.")

class IWillAttemptTransaction(ILoopEvent):
    """
    Base class for attempt events.
    """
    tx = Attribute("The transaction.")
    attempt_number = Attribute("The number of the attempt. Starts at 0.")

# We get this in Python 2
# pylint:disable=too-many-ancestors

class IWillFirstAttempt(IWillAttemptTransaction):
    """
    The first attempt.
    """

class IWillRetryAttempt(IWillAttemptTransaction):
    """
    A retry attempt.
    """

class IWillLastAttempt(IWillRetryAttempt):
    """
    The final retry.
    """

class IWillSleepBetweenAttempts(ILoopEvent):
    """
    Will sleep between attempts.

    If the ``sleep_time`` attribute is modified,
    that will be the time slept.
    """
    sleep_time = Attribute("The time to sleep.")


class IWillFirstAttemptWithRequest(IWillFirstAttempt):
    """
    The first attempt, but with a request object.

    .. versionadded:: 4.2.0
    """
    request = Attribute("The request object that will be used.")


class IWillRetryAttemptWithRequest(IWillRetryAttempt):
    """
    A retry attempt with a request object.

    .. versionadded:: 4.2.0
    """
    request = Attribute("The request object that will be used.")


class IWillLastAttemptWithRequest(IWillLastAttempt):
    """
    The final retry with a request object.

    .. versionadded:: 4.2.0
    """
    request = Attribute("The request object that will be used.")

@implementer(ILoopInvocation)
class LoopInvocation(object):
    __slots__ = ('loop', 'handler', 'args', 'kwargs')

    def __init__(self, loop, handler, args, kwargs):
        self.loop = loop
        self.handler = handler
        self.args = args
        self.kwargs = kwargs


@implementer(ILoopEvent)
class LoopEvent(object):
    __slots__ = ('invocation',)
    def __init__(self, invocation):
        self.invocation = invocation

    @property
    def handler_args(self):
        return self.invocation.args

    @property
    def handler_kwargs(self):
        return self.invocation.kwargs

@implementer(IAfterTransactionBegan)
class AfterTransactionBegan(LoopEvent):
    __slots__ = ('tx',)
    def __init__(self, invocation, tx):
        LoopEvent.__init__(self, invocation)
        self.tx = tx

@implementer(IWillAttemptTransaction)
class WillAttemptTransaction(LoopEvent):
    __slots__ = ('tx', 'attempt_number')
    def __init__(self, invocation, tx, attempt_number):
        LoopEvent.__init__(self, invocation)
        self.tx = tx
        self.attempt_number = attempt_number

@implementer(IWillFirstAttempt)
class WillFirstAttempt(WillAttemptTransaction):
    __slots__ = ()

@implementer(IWillRetryAttempt)
class WillRetryAttempt(WillAttemptTransaction):
    __slots__ = ()

@implementer(IWillLastAttempt)
class WillLastAttempt(WillRetryAttempt):
    __slots__ = ()

@implementer(IWillSleepBetweenAttempts)
class WillSleepBetweenAttempts(LoopEvent):
    __slots__ = ('sleep_time',)

    def __init__(self, invocation, sleep_time):
        LoopEvent.__init__(self, invocation)
        self.sleep_time = sleep_time

class _RequestMixin(object):
    @property
    def request(self):
        return self.handler_args[0]

@implementer(IWillFirstAttemptWithRequest)
class WillFirstAttemptWithRequest(WillFirstAttempt, _RequestMixin):
    __slots__ = ()

@implementer(IWillRetryAttemptWithRequest)
class WillRetryAttemptWithRequest(WillRetryAttempt, _RequestMixin):
    __slots__ = ()

@implementer(IWillLastAttemptWithRequest)
class WillLastAttemptWithRequest(WillLastAttempt, _RequestMixin):
    __slots__ = ()
