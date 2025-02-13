from setuptools import setup, find_packages

setup(
    name="portfolio_tracker",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pymongo",
        "yfinance",
        "python-dotenv",
        "pytz",
    ],
    author="Ankit Pachauri",
    author_email="ankitpachauri3@example.com",
    description="A portfolio tracking system with multi-exchange support",
    keywords="portfolio, stocks, trading, mongodb",
    python_requires=">=3.8",
) 