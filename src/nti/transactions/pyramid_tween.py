#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A Pyramid tween that begins and ends transactions around its handler
using the :class:`nti.transactions.loop.TransactionLoop`.

This very similar to earlier versions of :mod:`pyramid_tm`, but with
the following substantial differences:

    - The transaction is rolled back if the request is deemed to be
      side-effect free (this has intimate knowledge of the paths that
      do not follow the HTTP rules for a GET being side-effect free;
      however, if you are a GET request and you violate the rules by
      having side-effects, you can set the environment key
      ``nti.request_had_transaction_side_effects`` to ``True``)

    - Logging is added to account for the time spent in aborts and
      commits.

    - Later versions of :mod:`pyramid_tm` were split into two parts,
      with :mod:`pyramid_retry` being used to handle retry using an
      "execution policy", which was new in Pyramid 1.9. This library
      is compatible with all versions of Pyramid from 1.2 onward.

Install this tween using the ``add_tween`` method::

    pyramid_config.add_tween(
        'nti.transactions.pyramid_tween.transaction_tween_factory',
        under=pyramid.tweens.EXCVIEW)

You may install it under or over the exception view, depending on whether you
need the transaction to be active in exception views.

If you have a tween that manages a ZODB connection, it should be installed
*above* this tween. That's because ZODB connections cannot be closed while
joined to a transaction; the transaction must be committed or aborted first.
"""

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

logger = __import__('logging').getLogger(__name__)

from nti.transactions._httpexceptions import HTTPBadRequest
from nti.transactions._httpexceptions import HTTPException
from nti.transactions._loglevels import TRACE
from nti.transactions.loop import TransactionLoop

__all__ = [
    'commit_veto',
    'is_side_effect_free',
    'is_error_retryable',
    'is_last_attempt',
    'TransactionTween',
    'transaction_tween_factory',
]

def commit_veto(request, response):
    """
    When used as a commit veto, the logic in this function will cause
    the transaction to be aborted if:

        - An ``X-Tm`` response header with the value ``'abort'`` (or
          any value other than ``'commit'``) exists. A value of
          ``'commit'`` overrides any later match in this list.

        - The response status code starts with ``'4'`` or ``'5'``.

        - The request environment has a true value for
          ``'nti.commit_veto'``

    Otherwise the transaction will be allowed to commit.
    """
    xtm = response.headers.get('x-tm')
    if xtm is not None:
        return xtm != 'commit'
    if response.status.startswith(('4', '5')):
        return True
    return request.environ.get('nti.commit_veto')

def is_side_effect_free(request):
    """
    Is the request side-effect free? If the answer is yes, we should
    be able to quietly abort the transaction and avoid taking out any
    locks in the DBs.

    A request is considered to be free of side effects if:

        - It is a GET or HEAD request; AND

        - The URL DOES NOT match a configured exception list.

    In this version, the configured exception list is not actually
    configurable. It is hardcoded to handle the case of socket.io
    polling (which does have side effects on GET requests), while
    still supporting serving the static resources of socket.io.
    """
    if request.method == 'GET' or request.method == 'HEAD':
        # GET/HEAD requests must NEVER have side effects.
        if 'socket.io' in request.url:
            # (Unfortunately, socket.io polling does)
            # However, the static resources don't.

            # TODO: This needs to be configurable *and* fast.
            #
            # A hardcoded nested conditional using `in` takes 224ns when the
            # answer is yes, and 218ns when it's no but still contains
            # socket.io, and 178ns when it's not even close --- we
            # expect that last case to be the common case. Changing the
            # first 'in' to be startswith('/socket.io') counter-intuitively slows
            # down the common case to be 323ns.
            #
            # A hardcoded regex match takes 438ns when the answer is yes,
            # 455ns when its no but still starts with socket.io, and
            # 390ns when it's not close. So twice as bad in the common case.
            # (All timings from CPython 2.7; revisit on PyPy and Python 3)
            return 'static' in request.url
        return True
    # Every non-get probably has side effects
    return False


def is_last_attempt(request):
    """
    Return `True` if the request is on its last attempt, meaning that
    the `TransactionTween` will not invoke the handler again, regardless
    of what happens during this attempt.
    """
    environ = request.environ
    attempt = environ.get('retry.attempt')
    attempts = environ.get("retry.attempts")

    return True if attempt is None or attempts is None else attempt + 1 == attempts


def is_error_retryable(request, exc):
    """
    Return `True` if the exception is one that can be retried.

    This will return `False` if the request is on its last attempt.
    """
    if is_last_attempt(request) or 'nti.transaction_tween_retryable' not in request.environ:
        return False

    return request.environ['nti.transaction_tween_retryable'](exc)


class TransactionTween(TransactionLoop):
    """
    A Pyramid tween for retrying execution of a request.

    When the request body is executing, the functions :func:`is_last_attempt`
    and :func:`is_error_retryable` can be used to influence handler behaviour.
    """

    def prep_for_retry(self, attempts_remaining, tx, request): # pylint:disable=arguments-differ
        """
        Prepares the request for possible retries.

        Buffers the body if needed using
        :meth:`pyramid.request.Request.make_body_seekable`.

        The first time this is called for a given request, if the method is
        expected to have a body and the body appears to be JSON, but
        the content type specifies a browser form submission, the
        content type is changed to be ``application/json``. This is a
        simple fix for broken clients that forget to set the HTTP
        content type. This may be removed in the future.

        .. caution::
            This doesn't do anything with the WSGI
            environment or request object; changes to those persist
            between retries.
        """
        # make_body_seekable will copy wsgi.input if necessary,
        # otherwise it will rewind the copy to position zero
        try:
            request.make_body_seekable()
        except IOError as e:
            # almost always " unexpected end of file reading request";
            # (though it could also be a tempfile issue if we spool to
            # disk?) at any rate,
            # this is non-recoverable
            logger.log(TRACE, "Failed to make request body seekable",
                       exc_info=True)
            # TODO: Should we do anything with the request.response? Set an error
            # code? It won't make it anywhere...

            # However, it is critical that we return a valid Response
            # object, even if it is an exception response, so that
            # Pyramid doesn't blow up

            raise self.AbortException(HTTPBadRequest(str(e)),
                                      "IOError on reading body")

        attempts = self.attempts
        # Starting at 0 for compatibility with pyramid_retry.
        attempt_number = attempts - attempts_remaining - 1
        request.environ['retry.attempt'] = attempt_number
        request.environ['retry.attempts'] = attempts
        request.environ['nti.transaction_tween_retryable'] = lambda ex: self._retryable(
            tx, (None, ex, None)
        )

        # WebTest, browsers, and many of our integration tests by
        # default sets a content type of
        # 'application/x-www-form-urlencoded' If you happen to access
        # request.POST, though, (like locale negotiation does, or
        # certain template operations do) the underlying WebOb will
        # notice the content-type and attempt to decode the body based
        # on that. This leads to a badly corrupted body (if it was
        # JSON) and mysterious failures; this has been seen in the
        # real world. An internal implementation change (accessing
        # POST) suddenly meant that we couldn't read their body.
        # Unfortunately, the mangling is not fully reversible, since
        # it wasn't encoded in the first place.

        # We attempt to fix that here. (This is the best place because
        # we are now sure the body is seekable.)
        if attempt_number == 0 \
           and request.method in ('POST', 'PUT') \
           and request.content_type == 'application/x-www-form-urlencoded':
            # This needs tested.
            body = request.body
            # Python 3 treats bytes different than strings. Iteration
            # and indexing don't iterate over one-byte strings, they return
            # *integers*. 123 and 91 are the integers for { and [
            if body and body[0] in (b'{', b'[', 123, 91):
                # encoded data will never start with these values, they would be
                # escaped. so this must be meant to be JSON
                request.content_type = 'application/json'

    def should_abort_due_to_no_side_effects(self, request): # pylint:disable=arguments-differ
        """
        Tests with :func:`is_side_effect_free`.

        If the request's ``environ`` has a true value for the key
        ``'nti.request_had_transaction_side_effects'``, this method will return
        false.
        """
        return  is_side_effect_free(request) and \
                not request.environ.get('nti.request_had_transaction_side_effects')

    def should_veto_commit(self, response, request): # pylint:disable=arguments-differ
        """
        Tests with :func:`commit_veto`.
        """
        return  commit_veto(request, response)

    def describe_transaction(self, request): # pylint:disable=arguments-differ
        return request.path_info

    def run_handler(self, request): # pylint:disable=arguments-differ
        try:
            return TransactionLoop.run_handler(self, request)  # Not super() for speed
        except HTTPException as e:
            # Pyramid catches these and treats them as a response. We
            # MUST catch them as well and let the normal transaction
            # commit/doom/abort rules take over--if we don't catch
            # them, everything appears to work, but the exception
            # causes the transaction to be aborted, even though the
            # client gets a response.
            #
            # The problem with simply catching exceptions and returning
            # them as responses is that it bypasses pyramid's notion
            # of "exception views". At this writing, we are only
            # using those to turn 403 into 401 when needed, but it
            # can also be used for other things (such as redirecting what
            # would otherwise be a 404).
            # So we wrap up __call__ and also check for HTTPException there
            # and raise it safely after transaction handling is done.
            # Of course, this is only needed if the exception was actually
            # raised, not deliberately returned (commonly HTTPFound and the like
            # are returned)...raising those could have unintended consequences
            request._nti_raised_exception = True
            return e

    def __call__(self, request): # pylint:disable=arguments-differ
        result = TransactionLoop.__call__(self, request)  # not super() for speed
        if  isinstance(result, HTTPException) and \
            getattr(request, '_nti_raised_exception', False):
            raise result
        return result

def transaction_tween_factory(handler, registry):
    """
    The factory to create the tween.

    The *registry* argument from Pyramid is used to access the
    Pyramid "deployment settings" to configure the behaviour
    of the transaction loop. The following settings are used.

    retry.attempts
        Int. The number of retry attempts. See :attr:`.TransactionLoop.attempts`
        for the default.
    retry.long_commit_duration
        Float. The number of seconds after which a commit will be considered
        "too long" and a warning logging message issued. See
        :attr:`.TransactionLoop.long_commit_duration` for the default.
    retry.sleep_ms
        Int. The base number of **milliseconds** to sleep between retry attempts.
        See :attr:`.TransactionLoop.sleep` for more documentation.

    See :class:`TransactionTween`
    """
    settings = registry.settings
    def setting(name, converter):
        v = settings.get(name, None)
        if v is not None:
            v = converter(v)
        return v

    attempts = setting('retry.attempts', int)
    retries = attempts - 1 if attempts else None

    sleep_ms = setting('retry.sleep_ms', int)
    sleep = sleep_ms / 1000 if sleep_ms else None

    long_commit_duration = setting('retry.long_commit_duration', float)


    tween = TransactionTween(handler,
                             retries=retries,
                             sleep=sleep,
                             long_commit_duration=long_commit_duration)
    logger.info("Created tween %s", tween)
    return tween
