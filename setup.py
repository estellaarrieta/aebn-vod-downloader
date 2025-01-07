from setuptools import find_packages, setup

setup(
    name='aebndl',
    version='0.4.10',
    packages=find_packages(),
    install_requires=[
        'lxml',
        'curl_cffi==0.7.4',
        'tqdm',
    ],
    entry_points={
        'console_scripts': ['aebndl = aebn_dl.cli:main']
    },
)
