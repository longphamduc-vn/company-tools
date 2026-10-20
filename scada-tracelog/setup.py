# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name="scada-tracelog",
    version="1.0.0",
    author="SCADA Optimization Team",
    description="Industrial SCADA Recipe Change Tracker & 256-Column Data Loss Guard",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "pandas>=2.0.0",
        "openpyxl>=3.1.0",
        "xlrd>=2.0.1",
    ],
    entry_points={
        "console_scripts": [
            "scada-tracelog=scada_tracelog.app:main",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
