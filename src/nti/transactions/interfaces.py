#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Interfaces for nti.transactions.

"""

from __future__ import print_function, absolute_import, division

from transaction.interfaces import TransactionError

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
