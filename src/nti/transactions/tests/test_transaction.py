#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, division

import unittest

from hamcrest import assert_that
from hamcrest import contains

from ..transactions import do
from ..transactions import do_near_end

import transaction

class TestDataManagers(unittest.TestCase):

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
