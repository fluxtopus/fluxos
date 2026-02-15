from setuptools import setup, find_packages

setup(
    name="mimic-sdk",
    version="0.1.0",
    description="Python SDK for Mimic Notification Service",
    author="Mimic Team",
    packages=find_packages(),
    install_requires=[
        "httpx>=0.25.1",
    ],
    python_requires=">=3.8",
)

