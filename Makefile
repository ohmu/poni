rst2html=rst2html

all: poni/version.py dist doc readme

include package.mk

poni/version.py: version.py
	python $< $@

dist: doc readme
	python setup.py sdist

doc:
	make -C doc html

readme: README.html

README.txt: README.html
	lynx $< -dump > $@

README.html: README.rst LICENSE
	$(rst2html) $< $@

clean: deb-clean
	$(RM) -r dist/ build/ poni.egg-info/ cover/
	$(RM) poni/version.py poni/*.pyc tests/*.pyc *.pyc README.html README.txt \
		examples/puppet/README.html examples/db-cluster/README.html
	$(RM) ../poni?$(shell git describe)* \
		../poni?$(shell git describe --abbrev=0)-*.tar.gz
	$(MAKE) -C doc clean

build-dep:
	apt-get --yes install python-setuptools python-docutils lynx

test-dep:
	apt-get --yes install pylint nosetests

pep8:
	pep8 --ignore=E501 poni/*.py

pylint:
	python -m pylint.lint --rcfile=pylintrc poni/*.py

tests:
	nosetests --processes=2

coverage:
	nosetests --with-coverage --cover-package=poni --cover-html

.PHONY: readme
.PHONY: coverage
.PHONY: tests
.PHONY: dist
.PHONY: doc
