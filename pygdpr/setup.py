from setuptools import setup, find_packages
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read()
setup(
    name = 'gdprCrawlerTest16',
    version = '0.0.1',
    author = 'Chen Sun, Supreeth Shastri, Evan Jacobs',
    author_email = 'evanalexjacob@gmail.com',
    license = 'MIT License',
    description = 'GDPR document crawler',
    long_description = long_description,
    long_description_content_type = "text/markdown",
    url = 'https://github.com/transientCloud/gdpr-sota',
    py_modules = ['gdprCrawler'],
    packages = find_packages(),
    include_package_data=True,
    install_requires = [requirements],
    python_requires='>=3.9',
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "Operating System :: MacOS",
    ],
    entry_points = '''
        [console_scripts]
        gdprCrawler=gdprCrawler:cli
    '''
)
