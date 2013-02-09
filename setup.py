from setuptools import setup, find_packages

PACKAGE = 'TracScheduled'
VERSION = '1.0'

setup(
	name=PACKAGE,
	version=VERSION,
	packages=find_packages(exclude=['*.tests*']),
	entry_points = {
		'trac.plugins': [
			'%s = scheduled' % PACKAGE,
		],
	},
	package_data={'scheduled': ['templates/*.html', 'htdocs/css/*.css']},
)
