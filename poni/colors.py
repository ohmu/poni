CODES = {
    'reset': '\033[1;m',
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
}

CODES.update({
    'key' : '\033[0;36m',
    'cloudkey' : '\033[0;35m',
    'str' : '\033[0;32m',
    'bool' : CODES['yellow'],
    'int' : CODES['white'],
    })

class Output:
    def __init__(self, out_file):
        self.out = out_file
        if hasattr(out_file, 'isatty') and out_file.isatty():
            self.color = lambda text, code: "%s%s%s" % (CODES[code],
                                                        text,
                                                        CODES["reset"])
        else:
            self.color = lambda text, code: text

    def value_repr(self, value):
        if isinstance(value, unicode):
            try:
                value = repr(value.encode("ascii"))
            except UnicodeEncodeError:
                pass

        if isinstance(value, dict):
            return "{%s}" % self.color_items(value.iteritems())
        elif isinstance(value, str):
            return self.color(value, "str")
        elif isinstance(value, bool):
            return self.color(value, "bool")
        elif isinstance(value, (int, long)):
            return self.color(value, "int")

        return repr(value)

    def color_items(self, items, key_color="key"):
        output = " ".join(("%s:%s" % (self.color(k, key_color),
                                      self.color(self.value_repr(v), "reset"))
                           for k, v in sorted(items)))
        if not output:
            output = self.color("none", "gray")

        return output

    def sendline(self, msg):
        self.out.write(msg)
        self.out.write("\n")
        self.flush()

    def flush(self):
        self.out.flush()


if __name__ == "__main__":
    for name, code in sorted(CODES.iteritems()):
        print "%s%s%s" % (code, name, CODES["reset"])
