
Changes
========

1.1.1 (2018-07-19)
------------------

- When the ``TransactionLoop`` raises a ``CommitFailedError`` from a
  ``TypeError``, it preserves the original message.


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
