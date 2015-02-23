"""
template rendering

Copyright (c) 2010-2012 Mika Eloranta
Copyright (c) 2013 Oskari Saarenmaa
See LICENSE for details.

"""

from . import errors
from io import StringIO
import re
import sys


if sys.version_info[0] == 2:
    string_types = basestring  # pylint: disable=E0602
else:
    string_types = str


try:
    # https://github.com/cheetahtemplate/cheetah/commit/bbca0d9e1db4710b523271399b3fae89d9993eb7
    from os.path import splitdrive
    import Cheetah.convertTmplPathToModuleName
    _unitrans = unicode(Cheetah.convertTmplPathToModuleName._pathNameTransChars)  # pylint: disable=E0602
    def _patched_convertTmplPathToModuleName(tmplPath):
        try:
            return splitdrive(tmplPath)[1].translate(_unitrans)
        except (UnicodeError, TypeError):
            return unicode(splitdrive(tmplPath)[1]).translate(_unitrans)  # pylint: disable=E0602
    Cheetah.convertTmplPathToModuleName.convertTmplPathToModuleName = _patched_convertTmplPathToModuleName

    import Cheetah.Template
    from Cheetah.Template import Template as CheetahTemplate

    import random

    # https://github.com/cheetahtemplate/cheetah/pull/2
    def _patched_genUniqueModuleName(baseModuleName):
        """
        Workaround the problem that Cheetah creates conflicting module names due to
        a poor module generator function. Monkey-patch the module with a workaround.

        Fixes failures that look like this:

          File "cheetah_DynamicallyCompiledCheetahTemplate_1336479589_95_84044.py", line 58, in _init_
          TypeError: super() argument 1 must be type, not None
        """
        if baseModuleName not in sys.modules:
            return baseModuleName
        else:
            return 'cheetah_%s_%x' % (baseModuleName, random.getrandbits(128))
    Cheetah.Template._genUniqueModuleName = _patched_genUniqueModuleName
except ImportError:
    CheetahTemplate = None

try:
    from mako.template import Template as MakoTemplate
    from mako.exceptions import MakoException
except ImportError:
    MakoTemplate = None

try:
    import genshi
    import genshi.template
except ImportError:
    genshi = None


_name_re = re.compile(r"(\\?\$(?:\{.+?\}|[._a-zA-Z0-9]+))")


def render_name(source_text, source_path, variables):
    """simplified filename rendering with dollar-variable substitution only"""
    if source_path:
        source_text = open(source_path).read()

    def sub(match):
        token = match.group(1)
        if token[0] == '\\':
            return token[1:]  # strip escape
        if token[1] == '{' and token[-1] == '}':
            token = token[2:-1]  # strip ${}
        else:
            token = token[1:]  # strip $
        node = variables
        tpath, _, targs = token.partition("(")
        for part in tpath.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = getattr(node, part)
        if callable(node):
            node = node(*eval("(" + targs)) if targs else node()  # pylint: disable=W0123
        if not isinstance(node, string_types):
            node = str(node)
        return node
    return _name_re.sub(sub, source_text)


def render_cheetah(source_text, source_path, variables):
    assert CheetahTemplate, "Cheetah is not installed"
    try:
        return str(CheetahTemplate(source=source_text, file=source_path, searchList=[variables]))
    except (Cheetah.Template.Error, SyntaxError, Cheetah.NameMapper.NotFound) as error:
        raise errors.TemplateError("{0}: {1}: {2}".format(source_path, error.__class__.__name__, error))


def render_mako(source_text, source_path, variables):
    assert MakoTemplate, "Mako is not installed"
    try:
        return MakoTemplate(text=source_text, filename=source_path).render(**variables)
    except MakoException as error:
        raise errors.TemplateError("{0}: {1}: {2}".format(source_path, error.__class__.__name__, error))


def render_genshi(source_text, source_path, variables):
    assert genshi, "Genshi is not installed"
    if source_path:
        source = open(source_path)
    else:
        source = StringIO(source_text)
    try:
        tmpl = genshi.template.MarkupTemplate(source, filepath=source_path)
        stream = tmpl.generate(**variables)
        return stream.render('xml')
    except (genshi.template.TemplateError, IOError) as error:
        raise errors.TemplateError("{0}: {1}: {2}".format(source_path, error.__class__.__name__, error))


def render(engine=None, source_text=None, source_path=None, variables=None):
    if engine in ("name", "poni"):
        return render_name(source_text, source_path, variables)
    elif engine == "cheetah":
        return render_cheetah(source_text, source_path, variables)
    elif engine in ("genshi", "xml"):
        return render_genshi(source_text, source_path, variables)
    elif engine == "mako":
        return render_mako(source_text, source_path, variables)
    else:
        raise errors.TemplateError("unknown rendering engine {0!r}".format(engine))
