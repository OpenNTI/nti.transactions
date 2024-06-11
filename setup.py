import codecs
from setuptools import setup, find_packages

version = '5.0.0'

entry_points = {
    'console_scripts': [
    ],
}

TESTS_REQUIRE = [
    'coverage',
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
    url='https://github.com/OpenNTI/nti.transactions',
    zip_safe=True,
    classifiers=[
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Framework :: ZODB',
    ],
    python_requires=">=3.8",
    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    namespace_packages=['nti'],
    tests_require=TESTS_REQUIRE,
    install_requires=[
        'six',
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
            'Sphinx',
            'repoze.sphinx.autointerface',
            'pyhamcrest',
            'furo; python_version >= "3.6"',
            'sphinx_rtd_theme; python_version < "3.6"',
        ],
        'pyramid': [
            'pyramid >= 1.2',
        ],
    },
    entry_points=entry_points
)
