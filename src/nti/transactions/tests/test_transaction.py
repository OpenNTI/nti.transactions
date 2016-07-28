#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""


.. $Id$
"""

from __future__ import print_function, absolute_import, division

#disable: accessing protected members, too many methods
#pylint: disable=W0212,R0904

import unittest
from hamcrest import assert_that
from hamcrest import is_
from hamcrest import calling
from hamcrest import raises

import fudge

from ..transactions import _do_commit
from ..interfaces import CommitFailedError

class TestCommit(unittest.TestCase):
    class RaisingCommit(object):
        def __init__(self, t=Exception):
            self.t = t

        def commit(self):
            if self.t:
                raise self.t()

    def test_commit_raises_type_error(self):
        assert_that(calling(_do_commit).with_args(self.RaisingCommit(TypeError),
                                                  '', 0),
                    raises(CommitFailedError))

    @fudge.patch('nti.transactions.transactions.logger.exception')
    def test_commit_raises_assertion_error(self, fake_logger):
        fake_logger.expects_call()

        assert_that(calling(_do_commit).with_args(self.RaisingCommit(AssertionError),
                                                  '', 0),
                    raises(AssertionError))

    @fudge.patch('nti.transactions.transactions.logger.exception')
    def test_commit_raises_value_error(self, fake_logger):
        fake_logger.expects_call()

        assert_that(calling(_do_commit).with_args(self.RaisingCommit(ValueError),
                                                  '', 0),
                    raises(ValueError))

    @fudge.patch('nti.transactions.transactions.logger.exception')
    def test_commit_raises_custom_error(self, fake_logger):
        fake_logger.expects_call()

        class MyException(Exception):
            pass

        try:
            raise MyException()
        except MyException:
            assert_that(calling(_do_commit).with_args(self.RaisingCommit(ValueError),
                                                      '', 0),
                        raises(MyException))

    @fudge.patch('nti.transactions.transactions.logger.warn')
    def test_commit_clean_but_long(self, fake_logger):
        fake_logger.expects_call()
        _do_commit(self.RaisingCommit(None), '', 0)
