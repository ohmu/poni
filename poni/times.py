import datetime

timediff = lambda a, b: str(datetime.timedelta(seconds=int(a - b)))

class Times:
    def __init__(self):
        self.entry = {}

    def add_task(self, task_id, name, start, stop):
        self.entry[task_id] = dict(name=name, start=start, stop=stop)

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
        first_start = min(e["start"] for e in self.entry.itervalues())
        last_stop = max(e["stop"] for e in self.entry.itervalues())
        out = []
        for key, prop in self.entry.iteritems():
            out.append((prop["start"],
                        "%s: %s" % (key, prop["name"]),
                        self.time_line(prop, first_start, last_stop),
                        self.pointer_line(prop, first_start, last_stop)))

        out.sort()
        longest = max(len(e[1]) for e in out)
        f = "%%-%ds %%s\n%%%ds %%s" % (longest, longest)
        for start, title, tl, pl in out:
            print f % (title, tl, "", pl)

