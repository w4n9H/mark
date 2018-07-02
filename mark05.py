"""
实现一个简单版本的multiprocessing
几个重要点
1.Process
2.Pool
3.Pipe
4.Queue
....
"""

import os
import sys
import itertools


class Popen:
    def __init__(self, process_obj):
        sys.stdout.flush()
        sys.stderr.flush()
        self.returncode = None

        self.pid = os.fork()
        if self.pid == 0:
            if 'random' in sys.modules:
                import random
                random.seed()
            code = process_obj._bootstrap()
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(code)


class Process:
    """ 实现一个简易版本的 multiprocessing.Proccess """
    def __init__(self, group=None, target=None, name=None, args=(), kwargs={}):
        self._popen = None
        self._parent_pid = os.getpid()
        self._target = target
        self._args = tuple(args)
        self._kwargs = dict(kwargs)

    def start(self):
        assert self._popen is None, 'cannot start a process twice'
        assert self._parent_pid == os.getpid(), \
            'can only start a process object created by current process'
        self._popen = Popen(self)

    def _bootstrap(self):
        global _current_process

        try:
            self._children = set()
            self._counter = itertools.count(1)
            try:
                sys.stdin.close()
                sys.stdin = open(os.devnull)
            except (OSError, ValueError):
                pass
            _current_process = self
            print('child process calling self.run()')
            try:
                self.run()
                exitcode = 0
            finally:
                pass
        finally:
            pass
        return exitcode

    def run(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


if __name__ == '__main__':
    p = Process()
    p.start()
