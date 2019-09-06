
=========
 Changes
=========

3.0.0 (2019-09-06)
==================

- Make ``TransactionLoop`` place its transaction manager in explicit
  mode. This can be faster and is easier to reason about, but forbids
  the called handler from manually calling ``begin()``, ``abort()`` or
  ``commit()``. See `issue 20
  <https://github.com/NextThought/nti.transactions/issues/20>`_.

- Move ``transaction.begin()`` out of the block of code that is
  retried. Previously, an error there would probably be raised
  *anyway* and not retried, unless a subclass had made customizations.

- Add ``setUp`` and ``tearDown`` methods to TransactionLoop to give
  subclasses a place to hook into the inners of the transaction loop.
  This is particularly helpful if they need to do something after the
  transaction manager has been put in explicit mode. See `issue 22
  <https://github.com/NextThought/nti.transactions/issues/22>`_.

2.0.1 (2019-09-03)
==================

- Fix compatibility with perfmetrics 3.0: drop ``from __future__
  import unicode_literals``.


2.0.0 (2018-07-20)
==================

- Use the new public ``isRetryableError`` in transaction 2.2. The
  interface for this package is unchanged, but a major version bump of
  a dependency necessitates a major bump here. See `issue 12
  <https://github.com/NextThought/nti.transactions/issues/12>`_.

- Test support for Python 3.7; remove test support for Python 3.4.

- ``TransactionLoop`` is more careful to not keep traceback objects
  around, especially on Python 2.

1.1.1 (2018-07-19)
==================

- When the ``TransactionLoop`` raises a ``CommitFailedError`` from a
  ``TypeError``, it preserves the original message.

- Test support for Python 3.6.

1.1.0 (2017-04-17)
==================

- Add a new ObjectDataManager that will attempt to execute after
  other ObjectDataManagers.


1.0.0 (2016-07-28)
==================

- Add support for Python 3.
- Eliminate ZODB dependency. Instead of raising a
  ``ZODB.POSException.StorageError`` for unexpected ``TypeErrors``
  during commit, the new class
  ``nti.transactions.interfaces.CommitFailedError`` is raised.
- Introduce a new subclass of ``TransactionError``,
  ``AbortFailedError`` that is raised when an abort fails due to a
  system error.
