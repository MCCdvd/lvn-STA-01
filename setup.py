from setuptools import find_packages, setup

setup(
    name="lvn-sta-01",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["pandas", "numpy", "scipy", "matplotlib", "click"],
)
