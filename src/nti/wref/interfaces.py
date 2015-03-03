#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Interfaces relating to weak references.

.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

from zope import interface

class IWeakRef(interface.Interface):
	"""
	Represents a weak reference to some object. The strategy for
	creating and maintaining weak references may vary dramatically for
	different types of objects, so the semantics associated with cleanup
	should not be assumed. For example, weak references to ordinary python
	objects can exist only within the lifetime of a single process
	and clear immediately when the original object is gone, but weak
	references to persistent objects may last for several processes and
	may persist even after the original object is gone.
	"""

	def __call__():
		"""
		Weak references are callable objects. Calling them returns
		the object they reference if it is still available, otherwise
		it returns ``None``.
		"""

	def __eq__(other):
		"""
		Weak references should be equal to other objects that
		weakly reference the same object.
		"""

	def __hash__():
		"""
		Weak references should be suitable for hashing.
		If possible, they should hash the same as the underlying object.
		"""

import weakref
interface.classImplements(weakref.ref, IWeakRef)

import persistent.wref
interface.classImplements(persistent.wref.WeakRef, IWeakRef)

class IWeakRefToMissing(IWeakRef):
	"""
	A weak reference that knows enough about the object it was
	referencing to be able to produce a :const:`.TYPE_MISSING` NTIID
	when the reference is clear (when calling this object returns ``None``).
	"""

	def make_missing_ntiid():
		"""
		Call this when the reference is clear to produce an NTIID
		that refers to the object that was referenced.

		Calling this before the reference is clear is not defined.
		"""


class ICachingWeakRef(IWeakRef):
	"""
	A weak ref that, as an implementation detail, may cache the referant.
	Whether or not to use that cached value is exposed as a keyword argument.
	"""

	def __call__( allow_cached=True ):
		"""
		Resolve the reference, as with :meth:`IWeakRef.call`; however, allows
		control of caching.

		:keyword allow_cached: If `True` (the default) a cached value can be used. If
			set to `False`, this will not return a cached value. Note, however, that,
			in a cluster, this may still return an object that other nodes might consider
			gone.
		"""
