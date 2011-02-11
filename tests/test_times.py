from poni import times
import random

def test_times():
    tasks = times.Times()
    for i in range(0, 10):
        start = random.uniform(1000, 2000)
        stop = start + random.uniform(1, 1000)
        tasks.add_task(i, "task%d" % i, start, stop)

    tasks.print_report()



