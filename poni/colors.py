"""
ANSI color code escapes for output

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""
from __future__ import print_function

CODES = {
    'reset': '\033[0;m',
    'gray' : '\033[1;30m',
    'red' : '\033[1;31m',
    'green' : '\033[1;32m',
    'yellow' : '\033[1;33m',
    'blue' : '\033[1;34m',
    'magenta' : '\033[1;35m',
    'cyan' : '\033[1;36m',
    'white' : '\033[1;37m',
    'crimson' : '\033[1;38m',
    'hred' : '\033[1;41m',
    'hgreen' : '\033[1;42m',
    'hbrown' : '\033[1;43m',
    'hblue' : '\033[1;44m',
    'hmagenta' : '\033[1;45m',
    'hcyan' : '\033[1;46m',
    'hgray' : '\033[1;47m',
    'lgreen' : '\033[0;32m',
    'lred' : '\033[0;31m',
    'lcyan' : '\033[0;36m',
    'lyellow' : '\033[0;33m',
    'bold': '\033[1m',
}

CODES.update({
    'key' : '\033[0;36m',
    'cloudkey' : '\033[0;35m',
    'str' : '\033[0;32m',
    'bool' : CODES['yellow'],
    'int' : CODES['bold'],
    'status': CODES['red'],
    'system': CODES['cyan'],
    'node': CODES['green'],
    'nodetype': CODES['lgreen'],
    'systemtype': CODES['lcyan'],
    'configtype': CODES['lyellow'],
    'config': CODES['yellow'],
    'configparent' : '\033[0;33m',
    'nodeparent' : '\033[0;32m',
    'header': CODES['cyan'],
    'path': CODES['lyellow'],
    'host': CODES['lyellow'],
    'command': CODES['bold'],
    'op_error': CODES['hred'],
    'op_ok': CODES['green'],
    'setting': CODES['reset'],
    'layer': CODES['reset'],
    'controls': CODES['lred'],
    'controlstype': CODES['lred'],
    None: CODES["reset"],
    })


class Output(object):
    def __init__(self, out_file, color="auto"):
        self.out = out_file
        if ((color == "on") or (color == "auto"
                                and (hasattr(out_file, 'isatty')
                                and out_file.isatty()))):
            self.color = lambda text, code: "%s%s%s" % (CODES[code],
                                                        text,
                                                        CODES["reset"])
        else:
            self.color = lambda text, code: text


if __name__ == "__main__":
    for name, code in sorted(CODES.items()):
        print("%s%s%s" % (code, name, CODES["reset"]))
