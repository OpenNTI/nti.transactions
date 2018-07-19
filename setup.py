import codecs
from setuptools import setup, find_packages

version = '1.1.1'

entry_points = {
    'console_scripts': [
    ],
}

TESTS_REQUIRE = [
    'zope.testrunner',
    'nti.testing',
    'fudge',
]

def _read(fname):
    with codecs.open(fname, encoding='UTF-8') as f:
        return f.read()

setup(
    name='nti.transactions',
    version=version,
    author='Jason Madden',
    author_email='jason@nextthought.com',
    description="NTI Transactions Utility",
    long_description=_read('README.rst') + _read('CHANGES.rst'),
    license='Apache',
    keywords='ZODB transaction',
    url='https://github.com/NextThought/nti.transactions',
    zip_safe=True,
    classifiers=[
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Development Status :: 5 - Production/Stable',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Framework :: ZODB',
    ],
    packages=find_packages('src'),
    package_dir={'': 'src'},
	include_package_data=True,
    namespace_packages=['nti'],
    tests_require=TESTS_REQUIRE,
    install_requires=[
        'setuptools',
        'dm.transaction.aborthook',
        'perfmetrics',
        'transaction',
        'zope.exceptions',
        'zope.interface',
    ],
    extras_require={
        'test': TESTS_REQUIRE,
        'gevent': ['gevent',]
    },
    entry_points=entry_points
)
