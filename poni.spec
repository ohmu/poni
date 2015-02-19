Name:           poni
Version:        %{major_version}
Release:        %{minor_version}%{?dist}
Summary:        simple system configuration management tool

Group:          Development/Languages
License:        ASL 2.0
Source0:        rpm-src-poni.tar

Requires:       python-argh, python-boto, python-dns, python-lxml, libvirt-python
BuildRequires:  pylint, pytest
BuildArch:      noarch

%description
Poni is a simple system configuration management tool.


%prep
%setup -q -n %{name}


%build
python2 setup.py build


%install
python2 setup.py install --skip-build --root %{buildroot}


%check
make PYTHON=python2 pylint tests


%files
%defattr(-,root,root,-)
%doc README.rst LICENSE doc
# For arch-specific packages: sitearch
%{_bindir}/*
%{python_sitelib}/*


%changelog
* Thu Feb 19 2015 Oskari Saarenmaa <os@ohmu.fi> - 0.7-150
- Refactored packaging, run tests, etc.

* Mon Jan 10 2011 Oskari Saarenmaa <os@ohmu.fi> - 0.4-0
- Update to 0.4; bundle into poni proper.

* Mon Dec 27 2010 Oskari Saarenmaa <os@ohmu.fi> - 0.3.1-0
- Update to 0.3.1.

* Thu Dec 23 2010 Oskari Saarenmaa <os@ohmu.fi> - 0.2-0
- Initial.
