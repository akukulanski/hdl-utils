import setuptools


install_requires = [
    'cocotb',
    'cocotb_bus',
    'amaranth',
    'amaranth-cocotb @ git+https://github.com/akukulanski/amaranth-cocotb.git@compat-cocotb-test-0.2.2',
    'pytest',
    'numpy',
]

setuptools.setup(
    name="hdl-utils",
    version="0.1.0",
    author="A. Kukulanski",
    author_email="akukulanski@gmail.com",
    description="HDL utils for Amaranth+Cocotb workflow",
    url="https://github.com/akukulanski/hdl-utils.git",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
    install_requires=install_requires,
)
