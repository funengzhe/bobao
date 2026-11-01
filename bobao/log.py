import sys
import time


def log(s):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), s, file=sys.stderr, flush=True)
