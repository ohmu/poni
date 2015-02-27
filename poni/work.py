"""
parallel task management

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

import logging
import threading
import time
try:
    import Queue as queue
except ImportError:
    import queue


class Task(threading.Thread):
    def __init__(self, target=None):
        threading.Thread.__init__(self, target=target)
        self.log = logging.getLogger("task")
        self.daemon = True
        self.runner = None
        self.start_time = None
        self.stop_time = None

    def can_start(self):
        return True

    def execute(self):
        assert False, "override in sub-class"

    def run(self):
        try:
            self.start_time = time.time()
            self.execute()
        finally:
            self.stop_time = time.time()
            self.runner.task_finished(self)


class Runner(object):
    def __init__(self, max_jobs=None):
        self.log = logging.getLogger("runner")
        self.not_started = set()
        self.started = set()
        self.stopped = set()
        self.finished_queue = queue.Queue()
        self.max_jobs = max_jobs

    def add_task(self, task):
        task.runner = self
        self.not_started.add(task)

    def task_finished(self, task):
        self.finished_queue.put(task)

    def check(self):
        for task in list(self.not_started):
            if self.max_jobs and (len(self.started) >= self.max_jobs):
                continue

            if not task.can_start():
                continue

            self.started.add(task)
            self.not_started.remove(task)
            task.start()

    def wait_task_to_finish(self):
        try:
            task = self.finished_queue.get(timeout=60.0)
        except queue.Empty:
            self.log.warning(
                "tasks taking long to finish: %s and %r tasks waiting to be started",
                ", ".join(str(task) for task in self.started), len(self.not_started))
            return

        self.log.debug("task %s finished, took %.2f seconds", task,
                       (task.stop_time - task.start_time))
        self.started.remove(task)
        self.stopped.add(task)
        self.finished_queue.task_done()

    def run_all(self):
        while self.not_started or self.started:
            self.check()
            self.wait_task_to_finish()
