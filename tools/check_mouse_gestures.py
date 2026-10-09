#!/usr/bin/env python3
# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Compiles and checks the stroke tracker shipped in the src/ overlay."""

import os
from pathlib import Path
import subprocess
import tempfile


SOURCE = r"""
#include <cassert>

#include "chrome/browser/ui/views/frame/mouse_gesture_tracker.h"

int main() {
  MouseGestureTracker tracker;
  tracker.Begin(100, 100);
  assert(tracker.active());
  assert(tracker.Finish(85, 100).empty());
  assert(!tracker.active());

  tracker.Begin(100, 100);
  assert(tracker.Finish(84, 100) == "L");

  tracker.Begin(100, 100);
  tracker.Update(80, 100);
  tracker.Update(60, 100);
  tracker.Update(50, 100);
  assert(tracker.Finish(66, 100) == "LR");

  tracker.Begin(100, 100);
  tracker.Update(80, 100);
  tracker.Update(64, 100);
  tracker.Update(64, 84);
  tracker.Update(64, 68);
  tracker.Update(80, 68);
  assert(tracker.Finish(80, 84) == "LURD");

  tracker.Begin(100, 100);
  tracker.Update(80, 100);
  tracker.Update(81, 101);
  tracker.Update(79, 99);
  assert(tracker.Finish(78, 100) == "L");

  tracker.Begin(0, 0);
  tracker.Update(0, 20);
  tracker.Update(0, 30);
  assert(tracker.Finish(0, 14) == "DU");

  tracker.Begin(100, 100);
  tracker.Update(80, 100);
  tracker.Cancel();
  assert(tracker.active());
  assert(tracker.cancelled());
  assert(tracker.Finish(60, 100).empty());
  assert(!tracker.active());

  tracker.Begin(0, 0);
  assert(!tracker.cancelled());
  for (int i = 0; i < 65; ++i) {
    tracker.Update(i % 2 ? 0 : -16, 0);
  }
  assert(tracker.cancelled());
  assert(tracker.Finish(0, 0).empty());
}
"""


def test_mouse_gesture_tracker():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        source = work / 'test.cc'
        source.write_text(SOURCE)
        binary = work / 'test'
        subprocess.run([
            os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra',
            '-Werror', '-I', str(root / 'src'), str(source), '-o', str(binary)
        ], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    test_mouse_gesture_tracker()
    print('Mouse gesture tracker checks passed.')
