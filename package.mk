version = $(shell git describe --long)
short_version = $(shell git describe --long | sed -e 's/-g.*//')
major_version = $(shell git describe --abbrev=0)
minor_version = $(shell git describe --long | sed -e 's,[^-]*-,,')

export DEBFULLNAME := Mika Eloranta
export DEBEMAIL := mika.eloranta@gmail.com

rpm: poni/version.py
	git archive -o rpm-src-poni.tar --prefix=poni/ HEAD
	# add poni/version.py to the tar, it's not in git repository
	tar -r -f rpm-src-poni.tar --transform=s-poni-poni/poni- poni/version.py
	rpmbuild -ta rpm-src-poni.tar \
		--define 'major_version $(major_version)' \
		--define 'minor_version $(subst -,.,$(minor_version))'
	$(RM) rpm-src-poni.tar

debian:
	python setup.py sdist -d ..
	cp "../poni-$(version).tar.gz" "../poni_$(short_version).orig.tar.gz"
	echo | dh_make -i -p "poni_$(version)" -c blank -f "../poni-$(version).tar.gz"
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
