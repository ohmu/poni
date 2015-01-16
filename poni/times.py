"""
timing reports

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

import sys
import json
import datetime
from . import util

timediff = lambda a, b: str(datetime.timedelta(seconds=int(a - b)))

class Times(object):
    def __init__(self):
        self.entry = []

    def load(self, file_path):
        self.entry = json.load(open(file_path))

    def save(self, file_path):
        util.json_dump(self.entry, file_path)

    def add_task(self, task_id, name, start, stop, args=None):
        self.entry.append(dict(task_id=task_id, name=name, start=start,
                               stop=stop, args=args))

    def positions(self, prop, start, stop):
        span = stop - start
        if not span:
            return "n/a"

        start_rel = (prop["start"] - start) / span
        stop_rel = (prop["stop"] - start) / span

        line_len = 70
        a = int(start_rel * line_len)
        b = int((stop_rel - start_rel) * line_len) or 1
        c = line_len - a - b
        return a, b, c

    def time_line(self, prop, start, stop):
        a, b, c = self.positions(prop, start, stop)
        pr = 10
        return "%s%s%s%s (%s)" % (
            " "*pr, "-" * a, "#" * b, "-" * c,
            timediff(prop["stop"], prop["start"]))

    def pointer_line(self, prop, start, stop):
        a, b, c = self.positions(prop, start, stop)
        if b == 1:
            t = ""
            b = 0
        else:
            t = "^"
            b -= 2

        t0 = timediff(prop["start"], start)
        t1 = timediff(prop["stop"], start)
        begin = a + 10 - len(t0) - 1
        return "%s%s ^%s%s %s" % (" " * begin, t0, " " * b, t, t1)

    def print_report(self):
        for chunk in self.iter_report():
            sys.stdout.write(chunk)

        sys.stdout.flush()

    def iter_report(self):
        if not self.entry:
            return

        first_start = min(e["start"] for e in self.entry)
        last_stop = max(e["stop"] for e in self.entry)
        out = []
        for prop in self.entry:
            out.append((prop["start"],
                        "%s: %s" % (prop["task_id"], prop["name"]),
                        self.time_line(prop, first_start, last_stop),
                        self.pointer_line(prop, first_start, last_stop)))

        out.sort()
        longest = max(len(e[1]) for e in out)
        f = "%%-%ds %%s\n%%%ds %%s\n" % (longest, longest)
        for start, title, tl, pl in out:
            yield f % (title, tl, "", pl)

