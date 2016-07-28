import codecs
from setuptools import setup, find_packages

version = '0.0.0.dev0'

entry_points = {
    'console_scripts': [
    ],
}

TESTS_REQUIRE = [
    'nose2[coverage_plugin]',
    'zope.testrunner',
    'nti.testing',
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
    long_description=_read('README.rst'),
    license='Apache',
    keywords='ZODB Transactions',
    classifiers=[
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: Implementation :: CPython'
    ],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    namespace_packages=['nti'],
    tests_require=TESTS_REQUIRE,
    install_requires=[
        'setuptools',
        'dm.transaction.aborthook',
        'perfmetrics',
        'transaction',
        'ZODB',
        'zope.exceptions',
        'zope.interface',
    ],
    extras_require={
        'test': TESTS_REQUIRE,
        'gevent': ['gevent',]
    },
    entry_points=entry_points
)
