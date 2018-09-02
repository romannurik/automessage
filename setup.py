import setuptools

with open('README.md', 'r') as fh:
  long_description = fh.read()

setuptools.setup(
  name='automessage',
  version='0.1.1',
  author='Roman Nurik',
  author_email='roman@nurik.net',
  description='Automatic protorpc message types for ndb.Model subclasses (Google App Engine only)',
  long_description=long_description,
  long_description_content_type='text/markdown',
  url='https://github.com/romannurik/automessage',
  packages=setuptools.find_packages(),
  keywords=['Google App Engine', 'GAE'],
  classifiers=[
    'Programming Language :: Python :: 2.7',
    'License :: OSI Approved :: Apache Software License',
    'Operating System :: OS Independent',
  ],
)