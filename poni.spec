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

This is the Python 2 package of Poni.

%if %{?python3_sitelib:1}0
%package -n python3-poni
Summary:        simple system configuration management tool (python 3)
Requires:       python3-argh, python3-boto, python3-dns, python3-lxml, libvirt-python3
BuildRequires:  python3-pylint, python3-pytest, %{requires}
BuildArch:      noarch

%description -n python3-poni
Poni is a simple system configuration management tool.

This is the Python 3 package of Poni.
%endif

%prep
%setup -q -n %{name}


%build
python2 setup.py build
%if %{?python3_sitelib:1}0
python3 setup.py build
%endif


%install
python2 setup.py install --skip-build --root %{buildroot}
mv %{buildroot}%{_bindir}/poni %{buildroot}%{_bindir}/poni-py2
sed -e "s@#!/bin/python@#!%{_bindir}/python@" -i %{buildroot}%{_bindir}/poni-py2
%if %{?python3_sitelib:1}0
python3 setup.py install --skip-build --root %{buildroot}
mv %{buildroot}%{_bindir}/poni %{buildroot}%{_bindir}/poni-py3
sed -e "s@#!/bin/python@#!%{_bindir}/python@" -i %{buildroot}%{_bindir}/poni-py3
%endif
ln -sf poni-py2 %{buildroot}%{_bindir}/poni


%check
make PYTHON=python2 pylint tests
%if %{?python3_sitelib:1}0
make PYTHON=python3 pylint tests
%endif


%files
%defattr(-,root,root,-)
%doc README.rst LICENSE doc
%{_bindir}/poni
%{_bindir}/poni-py2
%{python_sitelib}/*

%if %{?python3_sitelib:1}0
%files -n python3-poni
%defattr(-,root,root,-)
%doc README.rst LICENSE doc
%{_bindir}/poni-py3
%{python3_sitelib}/*
%endif


%changelog
* Thu Feb 26 2015 Oskari Saarenmaa <os@ohmu.fi> - 0.7-160
- Build and package python 3 version.

* Thu Feb 19 2015 Oskari Saarenmaa <os@ohmu.fi> - 0.7-150
- Refactored packaging, run tests, etc.

* Mon Jan 10 2011 Oskari Saarenmaa <os@ohmu.fi> - 0.4-0
- Update to 0.4; bundle into poni proper.

* Mon Dec 27 2010 Oskari Saarenmaa <os@ohmu.fi> - 0.3.1-0
- Update to 0.3.1.

* Thu Dec 23 2010 Oskari Saarenmaa <os@ohmu.fi> - 0.2-0
- Initial.
