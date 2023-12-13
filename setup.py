from setuptools import find_packages, setup

setup(
    name='aebndl',
    version='0.3.8',
    packages=find_packages(),
    install_requires=[
        'lxml',
        'curl-cffi',
        'tqdm',
    ],
    entry_points={
        'console_scripts': [
            'aebndl = aebn_dl.main:main'
        ]
    },
)
