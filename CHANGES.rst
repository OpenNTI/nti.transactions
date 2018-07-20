
Changes
========

2.0.0 (2018-07-20)
------------------

- Use the new public ``isRetryableError`` in transaction 2.2. The
  interface for this package is unchanged, but a major version bump of
  a dependency necessitates a major bump here. See `issue 12
  <https://github.com/NextThought/nti.transactions/issues/12>`_.

- Test support for Python 3.7; remove test support for Python 3.4.

- ``TransactionLoop`` is more careful to not keep traceback objects
  around, especially on Python 2.

1.1.1 (2018-07-19)
------------------

- When the ``TransactionLoop`` raises a ``CommitFailedError`` from a
  ``TypeError``, it preserves the original message.

- Test support for Python 3.6.

1.1.0 (2017-04-17)
------------------

- Add a new ObjectDataManager that will attempt to execute after
  other ObjectDataManagers.


1.0.0 (2016-07-28)
------------------

- Add support for Python 3.
- Eliminate ZODB dependency. Instead of raising a
  ``ZODB.POSException.StorageError`` for unexpected ``TypeErrors``
  during commit, the new class
  ``nti.transactions.interfaces.CommitFailedError`` is raised.
- Introduce a new subclass of ``TransactionError``,
  ``AbortFailedError`` that is raised when an abort fails due to a
  system error.
