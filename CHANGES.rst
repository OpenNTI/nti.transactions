
=========
 Changes
=========

5.0.0 (2024-06-11)
==================

- Add support for Python 3.12 and 3.13.
- Drop support for Python 2 and anything less than Python 3.8.
- Add the ability to specify a transaction manager for loops to use
  other than the default.


4.3.0 (2023-05-05)
==================

- Add support for Python 3.10 and 3.11.


4.2.1 (2021-05-25)
==================

- When aborting a transaction due to an exception, log the exception
  instead of just the exception type (twice). Exception messages can
  be very helpful in understanding exactly what went wrong and
  possibly how to fix it for transient errors (e.g., a
  ``ZODB.POSException.ConflictError`` includes the object ID and
  class, which can be used to reduce the conflicts). This makes the
  logging slightly more expensive (when enabled). See `PR 58
  <https://github.com/NextThought/nti.transactions/pull/58>`_.


4.2.0 (2021-02-11)
==================

- Add support for Python 3.9.
- Move CI from Travis CI to Github Actions.
- When the Pyramid tween retries, any volatile attributes (those
  beginning with ``_v_``) in the request dictionary are deleted. This
  is inspired by ``persistent`` and meant to facilitate safe caching.
  When compared to events sent by the transaction loop, there is no
  specified order. See `issue 54 <https://github.com/NextThought/nti.transactions/issues/54>`_.
- Fix various event classes not properly specifying the interface they
  implement. For example, ``WillFirstAttempt`` now properly implements
  ``IWillFirstAttempt``, and ``WilLRetryAttempt`` now properly
  implements ``IWillRetryAttempt``. See `issue 52
  <https://github.com/NextThought/nti.transactions/issues/52>`_.
- Add ``IWillLastAttempt`` as a subclass of ``IWillRetryAttempt`` and
  the last event emitted.
- The Pyramid tween now emits ``IWillRetryAttemptWithRequest``, et al,
  to provide simple access to the request object.

4.1.0 (2020-07-22)
==================

- Add logging to the pyramid tween transaction factory to show the
  settings that are in use.
- Add ``TransactionLoop.side_effect_free_log_level``, and change the
  default value to DEBUG. It is useful to set this to ERROR or higher
  in tests.
- Add ``TransactionLoop.side_effect_free_resource_limit``.


4.0.1 (2020-07-18)
==================

- Add missing dependency on zope.event.
- Fix raising ``AlreadyInTransaction`` error on the second and
  subsequent calls to a loop when a transaction synchronizer raises an
  error on the first call. See `issue 49
  <https://github.com/NextThought/nti.transactions/issues/49>`_.

4.0.0 (2019-12-13)
==================

- Require at least version 3.0 of the ``transaction`` package.

- Drop dependency on the ``dm.transaction.aborthook`` package. That
  functionality is now natively provided in transaction 3.0.


3.1.1 (2019-12-10)
==================

- Fix logging of long duration commits. See `issue 44
  <https://github.com/NextThought/nti.transactions/issues/44>`_.

- Add logging and a metric
  (``transaction.side_effect_free_violation``) for transactions that
  claim to have no side effects, but which actually result in joined
  resource managers. This can indicate unnecessarily throwing away
  work. See `issue 45 <https://github.com/NextThought/nti.transactions/issues/45>`_.


3.1.0 (2019-11-29)
==================

- Add support for Python 3.8.

- Refactor internal implementation details. Instead of importing
  everything from ``nti.transactions.transactions``, more specific
  modules are used to group objects by function. The old imports
  continue to work. In 4.0 they will generate a deprecation warning
  and in 5.0 they will be removed.

- Add a Pyramid tween to manage transactions and transaction retries.
  Various settings can be configured as Pyramid deployment settings
  (e.g., in the ini file).

- Make the transaction loop increase the time it sleeps between
  retries following the `random binary exponential backoff algorithm
  <https://en.wikipedia.org/wiki/Exponential_backoff>`_ used by Ethernet.

- Reduce the default number of attempts to 4 (one attempt and 3
  retries). See `issue 35 <https://github.com/NextThought/nti.transactions/issues/35>`_.

- Make the transaction loop emit more metrics. See `issue 31
  <https://github.com/NextThought/nti.transactions/issues/31>`_.

- Make commit logging now always happen at least at the debug level,
  escalating to warning for long commits. It also includes the number
  of retries taken and the amount of time spent sleeping. See `issue
  32 <https://github.com/NextThought/nti.transactions/issues/32>`_.

- Make the transaction loop emit events (using ``zope.event``) at certain parts of the
  transaction lifecycle. See `issue 33 <https://github.com/NextThought/nti.transactions/issues/33>`_.

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
