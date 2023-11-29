from setuptools import find_packages, setup

with open('requirements.txt') as f:
    required_packages = f.read().splitlines()

setup(
    name='aebndl',
    version='0.3.2',
    packages=find_packages(),
    install_requires=required_packages,
    entry_points={
        'console_scripts': [
            'aebndl = aebn_dl.aebn_dl:main'
        ]
    },
)
