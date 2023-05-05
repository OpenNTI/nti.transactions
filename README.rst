==================
 nti.transactions
==================


.. _transaction: https://pypi.python.org/pypi/transaction

.. image:: https://coveralls.io/repos/github/NextThought/nti.transactions/badge.svg?branch=master
	:target: https://coveralls.io/github/NextThought/nti.transactions?branch=master

.. image:: https://github.com/NextThought/nti.transactions/workflows/tests/badge.svg
   :target: https://github.com/NextThought/nti.transactions/actions?query=workflow%3Atests

.. image:: https://readthedocs.org/projects/ntitransactions/badge/?version=latest
   :target: https://ntitransactions.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

Extensions to the `transaction`_ package.



Transaction Management
======================

``nti.transactions.loop.TransactionsLoop`` is a retryable
transaction manager. It is conceptually similar to the `attempts`_
context manager provided by the transaction package itself, but much
more powerful and extensible via subclasses. Features include:

- Configurable commit vetos.
- Extensible tests for which exceptions should be retried.
- The ability to abort the transaction and bypass a potentially
  expensive commit when there are expected to be no side-effects.
- Sleeping between retries.
- Extensive logging and timing.

The TransactionLoop can be used as-is, or it can be subclassed for
customization. For use in a Pyramid tween, for example, a minimal
subclass might look like this (see ``nti.transactions.pyramid_tween``
for a full-featured tween)::

  >>> class PyramidTransactionLoop(TransactionLoop):
  ...    def prep_for_retry(self, number, request):
  ...        request.make_body_seekable()
  ...    def describe_transaction(self, request):
  ...        return request.url

Data Managers
=============

A few `data managers`_ are provided for convenience.

The first data manager is used to put an object in a ``queue``
(something with the ``full`` and ``put_nowait`` methods) when a
transaction succeeds. If the queue is full, then the transaction will
not be allowed to commit::

  >>> from nti.transactions.queue import put_nowait
  >>> put_nowait(queue, object)

This is a special case of the ``ObjectDataManager``, which will call
one method with any arguments when a transaction commits. It can be
configured to vote on whether the transaction should be allowed to commit.
or not. This is useful for, say, putting an item in a Redis queue when
the transaction is successful. It can be constructed directly, but the
``do`` function is a shorthand way of joining one to the current
transaction::

  >>> from nti.transactions.manager import do
  >>> do(print, args=("Committed"))

.. caution:: See the documentation of this object for numerous
	     warnings about side-effects and its interaction with the
	     transaction machinery. Use it with care!

.. _attempts: http://zodb.readthedocs.io/en/latest/transactions.html#retrying-transactions
.. _data managers: http://zodb.readthedocs.io/en/latest/transactions.html#data-managers
