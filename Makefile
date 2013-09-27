rst2html=rst2html

all: poni/version.py dist doc readme example-doc

include package.mk

poni/version.py: version.py
	python $< $@

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

pylint:
	python -m pylint.lint --disable=C0111,C0103,R0201,W0612,W0613,R0912,R0913,R0914 - --max-line-length 150 poni/*.py

tests:
	nosetests --processes=2

coverage:
	nosetests --with-coverage --cover-package=poni --cover-html

.PHONY: readme
.PHONY: coverage
.PHONY: tests
.PHONY: dist
.PHONY: doc
.PHONY: example-doc
