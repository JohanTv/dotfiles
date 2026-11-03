#!/usr/bin/env python3
"""Runner de pruebas unitarias para `plane-worktree`."""

import os
import sys
import unittest

if __name__ == "__main__":
    test_dir = os.path.dirname(os.path.abspath(__file__))
    loader = unittest.TestLoader()
    suite = loader.discover(test_dir, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)
