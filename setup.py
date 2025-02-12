from setuptools import setup, find_packages

setup(
    name="portfolio_tracker",
    packages=find_packages(),
    version="0.1.0",
    install_requires=[
        'pymongo>=3.12.0',
        'python-dotenv>=0.19.0',
        'pytz>=2021.3',
        'fastapi>=0.68.1',
        'uvicorn>=0.15.0',
        'pydantic>=1.8.2',
        'prometheus-client>=0.11.0',
        'pytest>=6.2.5',
        'redis>=3.5.3'
    ],
    author="Ankit Pachauri",
    author_email="ankitpachauri3@example.com",
    description="A portfolio tracking system with multi-exchange support",
    keywords="portfolio, stocks, trading, mongodb",
    python_requires=">=3.8",
) 