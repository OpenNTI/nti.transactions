#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, division

import unittest

from hamcrest import assert_that
from hamcrest import contains
from hamcrest import calling
from hamcrest import raises
from hamcrest import is_

from ..manager import do
from ..manager import do_near_end

import transaction


from nti.testing.base import AbstractTestBase


class TestDataManagerFunctions(unittest.TestCase):

    def test_data_manager_sorting(self):
        results = []
        def test_call(x):
            results.append(x)

        # The managers will execute in order added (since identical),
        # except for the one that requests to go last.
        do(call=test_call, args=(0,))
        do(call=test_call, args=(1,))
        do_near_end(call=test_call, args=(10,))
        do(call=test_call, args=(2,))
        transaction.commit()
        assert_that(results, contains(0, 1, 2, 10))


class TestObjectDataManager(AbstractTestBase):

    def test_vote(self):
        class Exc(Exception):
            pass
        def vote():
            raise Exc()

        odm = do(call=lambda: 1, vote=vote)
        assert_that(calling(odm.tpc_vote).with_args(None), raises(Exc))

    def test_callable_name(self):
        class X(object):
            def thing(self):
                pass

        x = X()
        odm = do(target=x, method_name='thing')
        assert_that(odm.callable, is_(x.thing))
