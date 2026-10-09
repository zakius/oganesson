// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_VIEWS_FRAME_MOUSE_GESTURE_TRACKER_H_
#define CHROME_BROWSER_UI_VIEWS_FRAME_MOUSE_GESTURE_TRACKER_H_

#include <algorithm>
#include <cmath>
#include <string>
#include <utility>

// Turns pointer positions into a chain of stroke directions, such as "LU".
// A direction is recorded after kStrokeDistance DIPs of dominant-axis movement,
// and repeated directions collapse into one stroke.
class MouseGestureTracker {
 public:
  void Begin(float x, float y) {
    anchor_x_ = extreme_x_ = x;
    anchor_y_ = extreme_y_ = y;
    strokes_.clear();
    active_ = true;
    cancelled_ = false;
  }

  void Update(float x, float y) {
    if (!active_ || cancelled_) {
      return;
    }
    float dx = x - anchor_x_;
    float dy = y - anchor_y_;
    // Measure reversals from the furthest observed point.
    if (!strokes_.empty()) {
      switch (strokes_.back()) {
        case 'L':
          extreme_x_ = std::min(extreme_x_, x);
          if (x - extreme_x_ >= kStrokeDistance) {
            dx = x - extreme_x_;
          }
          break;
        case 'R':
          extreme_x_ = std::max(extreme_x_, x);
          if (extreme_x_ - x >= kStrokeDistance) {
            dx = x - extreme_x_;
          }
          break;
        case 'U':
          extreme_y_ = std::min(extreme_y_, y);
          if (y - extreme_y_ >= kStrokeDistance) {
            dy = y - extreme_y_;
          }
          break;
        case 'D':
          extreme_y_ = std::max(extreme_y_, y);
          if (extreme_y_ - y >= kStrokeDistance) {
            dy = y - extreme_y_;
          }
          break;
      }
    }
    if (std::max(std::abs(dx), std::abs(dy)) < kStrokeDistance) {
      return;
    }
    const char direction = std::abs(dx) >= std::abs(dy)
                               ? (dx < 0 ? 'L' : 'R')
                               : (dy < 0 ? 'U' : 'D');
    if (strokes_.empty() || strokes_.back() != direction) {
      if (strokes_.size() == kMaxStrokes) {
        Cancel();
        return;
      }
      strokes_ += direction;
    }
    anchor_x_ = extreme_x_ = x;
    anchor_y_ = extreme_y_ = y;
  }

  std::string Finish(float x, float y) {
    Update(x, y);
    active_ = false;
    return cancelled_ ? std::string() : std::exchange(strokes_, {});
  }

  void Cancel() {
    cancelled_ = true;
    strokes_.clear();
  }

  bool active() const { return active_; }
  bool cancelled() const { return cancelled_; }

 private:
  static constexpr float kStrokeDistance = 16;
  // Bounds storage; longer gestures cancel.
  static constexpr size_t kMaxStrokes = 64;
  float anchor_x_ = 0;
  float anchor_y_ = 0;
  float extreme_x_ = 0;
  float extreme_y_ = 0;
  std::string strokes_;
  bool active_ = false;
  bool cancelled_ = false;
};

#endif  // CHROME_BROWSER_UI_VIEWS_FRAME_MOUSE_GESTURE_TRACKER_H_
