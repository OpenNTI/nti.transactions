import codecs
from setuptools import setup, find_packages

version = '4.1.0'

entry_points = {
    'console_scripts': [
    ],
}

TESTS_REQUIRE = [
    'coverage',
    'fudge',
    'nti.testing',
    'pylint',
    'pyramid',
    'zope.component',
    'zope.testrunner',
    'ZODB',
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
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
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
        'perfmetrics',
        'setuptools',
        'transaction >= 3.0.0',
        'zope.cachedescriptors',
        'zope.exceptions',
        'zope.interface',
        'zope.event',
    ],
    extras_require={
        'test': TESTS_REQUIRE,
        'gevent': ['gevent',],
        'docs': [
            'Sphinx >= 2.1.2',
            'repoze.sphinx.autointerface',
            'pyhamcrest',
            'sphinx_rtd_theme',
        ],
        'pyramid': [
            'pyramid >= 1.2',
        ],
    },
    entry_points=entry_points
)
