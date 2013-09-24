version = $(shell git describe --long)
short_version = $(shell git describe --long | sed -e 's/-g.*//')
major_version = $(shell git describe --abbrev=0)
minor_version = $(shell git describe --long | sed -e 's,[^-]*-,,')

path = $(realpath .)
base = $(shell basename $(path))

export DEBFULLNAME := Mika Eloranta
export DEBEMAIL := mika.eloranta@gmail.com

rpm: poni/version.py
	cd .. ; tar -zcv --exclude=*~ --exclude=.git -f $(base)-$(version).tar.gz $(base)
	rpmbuild -ta ../$(base)-$(version).tar.gz \
		--define 'full_version $(version)' \
		--define 'major_version $(major_version)' \
		--define 'minor_version $(subst -,_,$(minor_version))'

debian:
	python setup.py sdist -d ..
	cp "../poni-$(version).tar.gz" "../poni_$(short_version).orig.tar.gz"
	echo | dh_make -b -i -p "poni_$(version)" -c blank -f "../poni-$(version).tar.gz"
	rm debian/*ex debian/*EX debian/docs debian/README.Debian
	cp debian.in/* debian/
	dch -v $(version) -D unstable "TODO: message"

deb-debuild: debian
	debuild -us -uc

deb-clean:
	$(RM) -r debian/

deb: debian
	dpkg-buildpackage -A -us -uc

.PHONY: debian
