# -*- coding: utf-8 -*-
"""
Tests for pyramid_tween.py.

"""

import json
import unittest
import sys


from zope.component import getGlobalSiteManager
from transaction.interfaces import TransientError

from hamcrest import assert_that
from hamcrest import is_
from hamcrest import none
from hamcrest import has_entries
from hamcrest import contains_exactly
from hamcrest import is_not as does_not
from hamcrest import same_instance

from nti.testing.matchers import is_true
from nti.testing.matchers import is_false
from nti.testing.matchers import has_attr
from nti.testing.matchers import has_length
from nti.testing.matchers import validly_provides

from .. import pyramid_tween
from .._httpexceptions import HTTPBadRequest

# pylint:disable=protected-access,unnecessary-lambda-assignment

class MockRequest(object):

    method = 'GET'
    url = '/foo/bar'
    content_type = 'text/plain'
    body = None
    path_info = None
    make_body_seekable = lambda _: None

    def __init__(self, url=None):
        self.environ = {}
        self.url = url or self.url

class MockResponse(object):

    status = '200 OK'

    def __init__(self, headers=None, status=None):
        self.headers = {}
        self.headers.update(headers or {})
        self.status = status or self.status


class TestCommitVeto(unittest.TestCase):

    def _assert_aborts(self, req=None, rsp=None):
        assert_that(
            pyramid_tween.commit_veto(req, rsp),
            is_true()
        )

    def test_x_tm_abort(self):
        rsp = MockResponse(headers={'x-tm': 'abort'})
        self._assert_aborts(rsp=rsp)

    def test_x_tm_arbitrary(self):
        rsp = MockResponse(headers={'x-tm': 'anything'})
        self._assert_aborts(rsp=rsp)

    def test_status_4(self):
        rsp = MockResponse(status='4')
        self._assert_aborts(rsp=rsp)

    def test_status_5(self):
        rsp = MockResponse(status='5')
        self._assert_aborts(rsp=rsp)

    def test_x_tm_commit_overrides(self):
        rsp = MockResponse(headers={'x-tm': 'commit'}, status='500 Internal Error')
        assert_that(
            pyramid_tween.commit_veto(None, rsp),
            is_false()
        )


class TestSideEffectFree(unittest.TestCase):
    def _assert_free(self, req, free=True):
        assert_that(
            pyramid_tween.is_side_effect_free(req),
            is_true() if free else is_false()
        )

    def test_get(self):
        self._assert_free(MockRequest())

    def test_socketio_not_free(self):
        self._assert_free(
            MockRequest(url='socket.io'),
            free=False
        )
        self._assert_free(
            MockRequest(url='/socket.io/1/xhr-polling/0x2737c2a4c6b0cb4b?t=1574743462760'),
            free=False,
        )
        self._assert_free(
            MockRequest(url='prefix/socket.io/1/xhr-polling/0x2737c2a4c6b0cb4b?t=1574743462760'),
            free=False,
        )

    def test_static_socketio_free(self):
        self._assert_free(MockRequest(url='socket.io/static'))
        # Actual URL
        self._assert_free(
            MockRequest(url='/socket.io/static/socket.io.js')
        )
        # Prefix
        self._assert_free(
            MockRequest(url='prefix/socket.io/static/socket.io.js')
        )


class TestTransactionTween(unittest.TestCase):

    def _makeOne(self, handler=lambda request: MockResponse()):
        return pyramid_tween.TransactionTween(handler)

    def test_retry_attempts_in_environ(self):
        environs = []
        def handler(request):
            environs.append(request.environ.copy())
            raise TransientError

        loop = self._makeOne(handler)
        req = MockRequest()
        try:
            loop(req)
        except TransientError:
            pass
        assert_that(environs, has_length(3))
        assert_that(environs[0], has_entries('retry.attempt', 0,
                                             'retry.attempts', 3))
        assert_that(environs[1], has_entries('retry.attempt', 1,
                                             'retry.attempts', 3))
        assert_that(environs[2], has_entries('retry.attempt', 2,
                                             'retry.attempts', 3))

    def test_retry_attempts_reset_v_props(self):
        environs = []
        def handler(request):
            if not environs:
                # First time in.
                request._non_transient_private = 42
                request.non_transient_public = 24
                # It wasn't reset before beginning
                assert_that(request, has_attr('_v_from_before', 36))
                del request._v_from_before
            environs.append(request.environ.copy())
            assert_that(request, does_not(has_attr('_v_foo1')))
            assert_that(request, does_not(has_attr('_v_foo2')))
            assert_that(request, does_not(has_attr('_v_from_before')))
            assert_that(request, has_attr('_non_transient_private', 42))
            assert_that(request, has_attr('non_transient_public', 24))
            request._v_foo1 = 1
            request._v_foo2 = 2

            raise TransientError

        loop = self._makeOne(handler)
        req = MockRequest()
        req._v_from_before = 36 # pylint:disable=attribute-defined-outside-init
        try:
            loop(req)
        except TransientError:
            pass
        assert_that(environs, has_length(3))
        assert_that(environs[0], has_entries('retry.attempt', 0,
                                             'retry.attempts', 3))
        assert_that(environs[1], has_entries('retry.attempt', 1,
                                             'retry.attempts', 3))
        assert_that(environs[2], has_entries('retry.attempt', 2,
                                             'retry.attempts', 3))

    def test_retry_attempts_events(self):
        # pylint:disable=import-outside-toplevel
        # pylint:disable=too-many-locals
        from zope.event import subscribers

        from nti.transactions.interfaces import IAfterTransactionBegan
        from nti.transactions.interfaces import IWillFirstAttempt
        from nti.transactions.interfaces import IWillRetryAttempt
        from nti.transactions.interfaces import IWillLastAttempt

        from nti.transactions.interfaces import AfterTransactionBegan
        from nti.transactions.interfaces import WillFirstAttempt
        from nti.transactions.interfaces import WillRetryAttempt
        from nti.transactions.interfaces import WillLastAttempt

        from nti.transactions.interfaces import IWillFirstAttemptWithRequest
        from nti.transactions.interfaces import IWillRetryAttemptWithRequest
        from nti.transactions.interfaces import IWillLastAttemptWithRequest

        from nti.transactions.interfaces import WillFirstAttemptWithRequest
        from nti.transactions.interfaces import WillRetryAttemptWithRequest
        from nti.transactions.interfaces import WillLastAttemptWithRequest

        events = []
        subscribers.append(events.append)
        self.addCleanup(subscribers.remove, events.append)

        calls = []
        def handler(_):
            calls.append(1)
            raise TransientError

        loop = self._makeOne(handler)
        req = MockRequest()
        try:
            loop(req)
        except TransientError:
            pass
        assert_that(calls, has_length(3))

        assert_that(events, has_length(6))
        assert_that(events, contains_exactly(
            is_(AfterTransactionBegan),
            is_(WillFirstAttempt),

            is_(AfterTransactionBegan),
            is_(WillRetryAttempt),

            is_(AfterTransactionBegan),
            is_(WillLastAttempt),
        ))

        assert_that(events, contains_exactly(
            validly_provides(IAfterTransactionBegan),
            validly_provides(IWillFirstAttempt),

            validly_provides(IAfterTransactionBegan),
            validly_provides(IWillRetryAttempt),

            validly_provides(IAfterTransactionBegan),
            validly_provides(IWillLastAttempt),
        ))

        assert_that(events, contains_exactly(
            is_(AfterTransactionBegan),
            is_(WillFirstAttemptWithRequest),

            is_(AfterTransactionBegan),
            is_(WillRetryAttemptWithRequest),

            is_(AfterTransactionBegan),
            is_(WillLastAttemptWithRequest),
        ))

        assert_that(events, contains_exactly(
            validly_provides(IAfterTransactionBegan),
            validly_provides(IWillFirstAttemptWithRequest),

            validly_provides(IAfterTransactionBegan),
            validly_provides(IWillRetryAttemptWithRequest),

            validly_provides(IAfterTransactionBegan),
            validly_provides(IWillLastAttemptWithRequest),
        ))

        for i in (1, 3, 5):
            assert_that(events[i], has_attr(
                'request',
                is_(same_instance(req))))

    def test_is_last(self):
        is_lasts = []
        def handler(request):
            is_lasts.append(pyramid_tween.is_last_attempt(request))
            raise TransientError

        loop = self._makeOne(handler)
        req = MockRequest()
        try:
            loop(req)
        except TransientError:
            pass
        assert_that(is_lasts, has_length(3))
        assert_that(is_lasts, is_([False, False, True]))

    def test_is_retryable_true(self):
        is_retryable = []
        def handler(request):
            is_retryable.append(pyramid_tween.is_error_retryable(request, TransientError()))
            raise TransientError

        loop = self._makeOne(handler)
        req = MockRequest()
        try:
            loop(req)
        except TransientError:
            pass
        assert_that(is_retryable, has_length(3))
        assert_that(is_retryable, is_([True, True, False]))

    def test_is_retryable_false(self):
        is_retryable = []
        def handler(request):
            is_retryable.append(pyramid_tween.is_error_retryable(request, Exception()))

        loop = self._makeOne(handler)
        req = MockRequest()
        loop(req)
        assert_that(is_retryable, has_length(1))
        assert_that(is_retryable, is_([False]))


    def test_prep_for_retry_abort_on_IOError(self):
        loop = self._makeOne()
        class Request(MockRequest):
            def make_body_seekable(self):
                raise IOError

        with self.assertRaises(loop.AbortAndReturn) as exc:
            loop.prep_for_retry(None, None, Request())

        assert_that(exc.exception.response, is_(HTTPBadRequest))

    def test_prep_for_retry_replaces_content_type_of_list(self):
        req = MockRequest()
        req.content_type = 'application/x-www-form-urlencoded'
        req.body = json.dumps([]).encode('ascii')
        # GET is unchanged, body ignored.
        loop = self._makeOne()
        loop(req)
        assert_that(req.content_type, is_('application/x-www-form-urlencoded'))

        req.method = 'PUT'
        loop(req)
        assert_that(req.content_type, is_('application/json'))

    def test_prep_for_retry_replaces_content_type_of_dict(self):
        req = MockRequest()
        req.content_type = 'application/x-www-form-urlencoded'
        req.body = json.dumps({}).encode('ascii')

        loop = self._makeOne()
        loop(req)
        assert_that(req.content_type, is_('application/x-www-form-urlencoded'))

        req.method = 'POST'
        loop(req)
        assert_that(req.content_type, is_('application/json'))

    def test_should_abort_override(self):
        req = MockRequest()
        assert pyramid_tween.is_side_effect_free(req)

        loop = self._makeOne()
        assert_that(loop.should_abort_due_to_no_side_effects(req), is_true())

        req.environ['nti.request_had_transaction_side_effects'] = 42
        assert_that(loop.should_abort_due_to_no_side_effects(req), is_false())

    def test_run_handler_catches_httpexception(self):
        def handler(_req):
            raise HTTPBadRequest

        loop = self._makeOne(handler)
        req = MockRequest()
        res = loop.run_handler(req)

        assert_that(req, has_attr('_v_nti_raised_exception', True))
        assert_that(res, is_(HTTPBadRequest))

    def test_run_handler_throws(self):
        class MyExc(Exception):
            pass

        def handler(_req):
            raise MyExc

        loop = self._makeOne(handler)
        with self.assertRaises(MyExc):
            loop.run_handler(MockRequest())

    def test_call_raises_http_exception_when_raised(self):
        def handler(_req):
            raise HTTPBadRequest

        loop = self._makeOne(handler)
        with self.assertRaises(HTTPBadRequest):
            loop(MockRequest())

    def test_call_returns_http_exception_when_returned(self):
        def handler(_req):
            return HTTPBadRequest()

        loop = self._makeOne(handler)
        assert_that(loop(MockRequest()), is_(HTTPBadRequest))


class TestTransactionTweenFactory(unittest.TestCase):

    def setUp(self):
        try:
            from pyramid.config import Configurator
        except ModuleNotFoundError as ex:
            # pyramid 2.0.2 with webob 1.8.7 won't import on Python 3.13
            if sys.version_info[:2] == (3, 13):
                self.skipTest(str(ex))
        self.config = config = config = Configurator(registry=getGlobalSiteManager())
        config.setup_registry()

    def _makeOne(self, handler=None, **settings):
        self.config.registry.settings.update(settings)
        return pyramid_tween.transaction_tween_factory(handler, self.config.registry)

    def test_factory_simple(self):
        handler = 42

        loop = self._makeOne(handler)
        assert_that(loop, is_(pyramid_tween.TransactionTween))
        assert_that(loop, has_attr('handler', is_(handler)))
        assert_that(loop, has_attr('attempts', 3))
        assert_that(loop, has_attr('long_commit_duration', 6))
        assert_that(loop, has_attr('sleep', none()))

    def test_factory_attempts(self):
        loop = self._makeOne(**{'retry.attempts': 42})
        assert_that(loop.attempts, is_(42))

    def test_factory_long_commit(self):
        loop = self._makeOne(**{'retry.long_commit_duration': 42})
        assert_that(loop, has_attr('long_commit_duration', 42))

    def test_factory_sleep(self):
        loop = self._makeOne(**{'retry.sleep_ms': 10})
        assert_that(loop, has_attr('sleep', 0.01))
