"""
template rendering

Copyright (c) 2010-2012 Mika Eloranta
Copyright (c) 2013 Oskari Saarenmaa
See LICENSE for details.

"""

from . import errors
from cStringIO import StringIO

try:
    import Cheetah.Template
    from Cheetah.Template import Template as CheetahTemplate

    import random
    import sys
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
    raise

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


def render_cheetah(source_text, source_path, vars):
    assert CheetahTemplate, "Cheetah is not installed"
    try:
        return str(CheetahTemplate(source=source_text, file=source_path, searchList=[vars]))
    except (Cheetah.Template.Error, SyntaxError, Cheetah.NameMapper.NotFound) as error:
        raise errors.TemplateError("{0}: {1}: {2}".format(source_path, error.__class__.__name__, error))

render_name = render_cheetah

def render_mako(source_text, source_path, vars):
    assert MakoTemplate, "Mako is not installed"
    try:
        return MakoTemplate(text=source_text, filename=source_path).render(**vars)
    except MakoException as error:
        raise errors.TemplateError("{0}: {1}: {2}".format(source_path, error.__class__.__name__, error))

def render_genshi(source_text, source_path, vars):
    assert genshi, "Genshi is not installed"
    if source_path:
        source = open(source_path)
    else:
        source = StringIO(source_text)
    try:
        tmpl = genshi.template.MarkupTemplate(source, filepath=source_path)
        stream = tmpl.generate(**vars)
        return stream.render('xml')
    except (genshi.template.TemplateError, IOError) as error:
        raise errors.TemplateError("{0}: {1}: {2}".format(source_path, error.__class__.__name__, error))

def render(engine=None, source_text=None, source_path=None, vars=None):
    if engine in ("name", "poni"):
        return render_name(source_text, source_path, vars)
    elif engine == "cheetah":
        return render_cheetah(source_text, source_path, vars)
    elif engine in ("genshi", "xml"):
        return render_genshi(source_text, source_path, vars)
    elif engine == "mako":
        return render_mako(source_text, source_path, vars)
    else:
        raise errors.TemplateError("unknown rendering engine {0!r}".format(engine))
