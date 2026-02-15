from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tentackl",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Multi-agent workflow management system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/tentackl",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.104.1",
        "uvicorn[standard]>=0.24.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "asyncio-redis>=0.16.1",
        "celery>=5.3.4",
        "redis>=5.0.1",
        "asyncpg>=0.29.0",
        "sqlalchemy>=2.0.23",
        "alembic>=1.12.1",
        "click>=8.1.7",
        "rich>=13.7.0",
        "python-dotenv>=1.0.0",
        "structlog>=23.2.0",
        "httpx>=0.25.2",
        "cryptography>=43.0.1",
    ],
    entry_points={
        "console_scripts": [
            "tentackl=src.cli.main:cli",
        ],
    },
)
