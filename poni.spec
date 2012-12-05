%{!?python_sitearch: %define python_sitearch %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib(1)")}

Name:           poni
Version:        %{major_version}
Release:        %{minor_version}%{?dist}
Summary:        simple system configuration management tool

Group:          Development/Languages
License:        ASL 2.0
Source0:        poni-%{full_version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

BuildArch:	noarch
BuildRequires:  python-devel

Requires:	python-boto, python-argh

%description
Poni is a simple system configuration management tool.

%prep
%setup -q -n %{name}


%build
CFLAGS="$RPM_OPT_FLAGS" %{__python} setup.py build


%install
rm -rf $RPM_BUILD_ROOT
%{__python} setup.py install --skip-build --root $RPM_BUILD_ROOT


%clean
rm -rf $RPM_BUILD_ROOT


%files
%defattr(-,root,root,-)
%doc README.rst LICENSE doc
# For arch-specific packages: sitearch
%{_bindir}/*
%{python_sitelib}/*


%changelog
* Mon Jan 10 2011 Oskari Saarenmaa <oskari@saarenmaa.fi> - 0.4-0
- Update to 0.4; bundle into poni proper.

* Mon Dec 27 2010 Oskari Saarenmaa <oskari@saarenmaa.fi> - 0.3.1-0
- Update to 0.3.1.

* Thu Dec 23 2010 Oskari Saarenmaa <oskari@saarenmaa.fi> - 0.2-0
- Initial.
