Turn 1: Create `/workspace/build_helper.py` with the provided function.

import os

def build():
    mode = os.getenv("BUILD_MODE", "debug")
    os.system(f'echo "Building in {mode} mode" && {mode}')
