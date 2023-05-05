#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Support for data managers.
"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import interface

import transaction

from transaction.interfaces import IDataManagerSavepoint
from transaction.interfaces import ISavepointDataManager

__all__ = [
    'ObjectDataManager',
    'OrderedNearEndObjectDataManager',
    'do',
    'do_near_end',
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
        :param string method_name: The name of the attribute to get from `target`.
            Optional if `callable` is given.
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
