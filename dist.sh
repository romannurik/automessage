#!/bin/sh
rm -rf dist/
python setup.py sdist
echo "** Now run twine upload dist/*.tar.gz"