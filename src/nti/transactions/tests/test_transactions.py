# -*- coding: utf-8 -*-
"""
Tests for the (deprecated) transactions.py.

"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import unittest
import warnings

# pylint:disable=bad-option-value,import-outside-toplevel

class TestWarnings(unittest.TestCase):

    def test_add_abort_hook(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')

            import nti.transactions.transactions as T
            T.add_abort_hooks()

        self.assertEqual(len(w), 2, w)
        self.assertIn('is deprecated', str(w[0]))
        self.assertIn('test_transactions', str(w[0]))
        self.assertIn('add_abort_hooks', str(w[1]))
        self.assertIn('test_transactions', str(w[1]))
