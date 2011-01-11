rst2html=rst2html

all: dist doc readme example-doc

include package.mk

dist: doc readme
	python setup.py sdist

doc:
	(cd doc && make html)

readme: README.html

README.txt: README.html
	lynx $< -dump > $@

README.html: README.rst LICENSE
	$(rst2html) $< $@

example-doc: examples/puppet/README.html examples/db-cluster/README.html

examples/puppet/README.html: examples/puppet/README.rst
	$(rst2html) $< $@

examples/db-cluster/README.html: examples/db-cluster/README.rst
	$(rst2html) $< $@

clean: deb-clean
	rm -rf dist/ build/ poni.egg-info/ poni/*.pyc cover/ examples/puppet/README.html examples/db-cluster/README.html README.html README.txt *.pyc
	(cd doc && make clean)

build-dep:
	apt-get --yes install python-setuptools python-docutils lynx

test-dep:
	apt-get --yes install pylint nosetests

pylint:
	python -m pylint.lint poni/*.py

tests:
	nosetests

coverage:
	nosetests --with-coverage --cover-package=poni --cover-html

.PHONY: readme
.PHONY: coverage
.PHONY: tests
.PHONY: dist
.PHONY: doc
.PHONY: example-doc
