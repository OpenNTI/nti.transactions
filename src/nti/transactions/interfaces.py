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
