PYTHON ?= python
rst2html ?= rst2html

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
	apt-get --yes install python-setuptools python-docutils python-sphinx lynx

test-dep:
	apt-get --yes install pep8 pylint python-pytest \
		python-argh python-boto python-cheetah python-genshi python-git

pep8:
	pep8 --ignore=E501 poni/*.py

pylint:
	if $(PYTHON) -m pylint.lint --help-msg C0330 | grep -qF bad-continuation; \
	then $(PYTHON) -m pylint.lint --rcfile pylintrc --disable=C0325,C0330 poni; \
	else $(PYTHON) -m pylint.lint --rcfile pylintrc poni; \
	fi

tests:
	PYTHONPATH=. $(PYTHON) -m pytest -vv tests

travis:
	# Travis does a shallow clone and won't find tags with git describe
	echo "__version__ = '0.7-travis'" > poni/version.py
	git fetch https://github.com/jaraco/path.py 5.1
	git cat-file blob FETCH_HEAD:path.py > path.py
	make all pylint tests

.PHONY: readme
.PHONY: coverage
.PHONY: tests
.PHONY: dist
.PHONY: doc
