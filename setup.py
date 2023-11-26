from setuptools import setup, find_packages

with open('requirements.txt') as f:
    required_packages = f.read().splitlines()

setup(
    name='aebn-dl',
    version='0.3.0',
    packages=find_packages(),
    install_requires=required_packages,
    entry_points={
        'console_scripts': [
            'aebn-dl = aebn-dl.aebn_dl:main'
        ]
    },
)