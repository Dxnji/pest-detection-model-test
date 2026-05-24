# Camera Startup Troubleshooting Guide

## Problem: Camera doesn't provide first frame in 5 seconds

The robot's camera system has been enhanced with diagnostic tools to help identify and fix this issue. This guide explains the improvements and how to use them.

## What Changed

### 1. **Version Checking & Diagnostics**
The `CameraService` now includes:
- `diagnose()` - Checks OpenCV version, camera hardware, and driver capabilities
- `benchmark_first_frame()` - Measures actual startup latency
- Enhanced logging at each step of the startup process

### 2. **Better Logging**
When startup times out, you now get diagnostic info:
```
ERROR: Timeout waiting for first frame after 5.50s
  -> Camera thread is running but no frames received
     VideoCapture not opened
```

### 3. **Tracking First Frame Timestamp**
The capture loop now logs when the first frame is received:
```
INFO: First frame captured in 245.3ms
```

## How to Diagnose

### Quick Diagnostic (30 seconds)
```bash
python camera_diagnostic.py --quick
```

Checks:
- OpenCV version
- Camera hardware availability
- First-frame latency estimate

### Full Diagnostic with Benchmark (2-3 minutes)
```bash
python camera_diagnostic.py
```

Additionally runs 3 startup latency trials to measure actual performance and suggest timeout values.

### Check Specific Camera Device
```bash
python camera_diagnostic.py --device=1
```

## Common Issues and Fixes

### Issue 1: "Failed to open VideoCapture"
**Cause**: Camera hardware not detected or permissions issue

**Fixes**:
```bash
# Check connected cameras
ls -la /dev/video*

# Check permissions (should show rw access)
# May need: sudo usermod -a -G video $USER
```

### Issue 2: "Camera thread is running but no frames received"
**Cause**: Driver can open camera but can't read frames

**Fixes**:
1. Check camera isn't in use by another process
2. Try closing other applications using camera
3. Verify camera cable connection
4. Try device 1 if device 0 fails: `python camera_diagnostic.py --device=1`

### Issue 3: High first-frame latency (> 2 seconds)
**Cause**: Too much image processing or insufficient resources

**Fixes** (in `configs.py`):
```python
# Lower resolution to reduce processing
INFERENCE_WIDTH = 160   # from 320
INFERENCE_HEIGHT = 160  # from 320

# Reduce FPS if not needed
TARGET_FPS = 10  # from 15

# Increase frame skip to reduce processing
FRAME_SKIP = 8  # from 4
```

### Issue 4: Intermittent timeouts
**Cause**: Marginal latency or power/thermal issues

**Fixes**:
1. Increase timeout in `app.py`:
```python
# Change from:
if not self.camera_service.wait_for_first_frame(timeout=5.0):

# To:
if not self.camera_service.wait_for_first_frame(timeout=10.0):
```

2. Check thermal throttling:
```bash
# On Raspberry Pi
vcgencmd measure_temp
# If over 80°C, improve cooling
```

3. Verify adequate power supply (5V 2.5A+ recommended)

## Understanding the Logs

### During normal startup:
```
INFO: Opening camera device 0
INFO: Waiting for first frame (timeout=5.0s)...
DEBUG: Waiting... 0.1s elapsed (thread alive: True)
INFO: First frame received in 0.245s
```

### When something fails:
```
WARNING: cv2.VideoCapture failed to open
WARNING: Camera open failed, retrying
ERROR: Timeout waiting for first frame after 5.50s
  -> Camera thread is running but no frames received
     VideoCapture not opened
```

## Configuration Optimization

After running diagnostics, optimize in `configs.py`:

```python
# CAMERA CONFIGURATION

# For Raspberry Pi Camera (CSI):
CAMERA_DEVICE = 0
INFERENCE_WIDTH = 320    # Reduce if slow
INFERENCE_HEIGHT = 320   # Reduce if slow
FRAME_SKIP = 4          # Increase if CPU usage is high
TARGET_FPS = 15         # Reduce if intermittent timeouts

# For USB Camera:
CAMERA_DEVICE = 1       # May be /dev/video1
INFERENCE_WIDTH = 320   # USB cameras may not support all resolutions
INFERENCE_HEIGHT = 320
```

## Advanced Debugging

### Test camera directly with Python
```python
import cv2
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Failed to open camera")
else:
    # Try a few reads
    for i in range(10):
        ok, frame = cap.read()
        if ok:
            print(f"Frame {i}: {frame.shape}")
        else:
            print(f"Frame {i}: FAILED")
    cap.release()
```

### Check OpenCV backend
```python
import cv2
cap = cv2.VideoCapture(0)
backend = cap.get(cv2.CAP_PROP_BACKEND)
print(f"Backend: {backend}")  # 200 = v4l2, 0 = auto
cap.release()
```

### Monitor camera in realtime
```bash
# Simple frame capture
python -c "
from services.camera_service import CameraService
from pathlib import Path
cam = CameraService()
cam.test_mode(run_seconds=10, save_debug_frame=Path('test_frame.jpg'))
"
```

## Summary

The enhanced camera system provides:
1. **`diagnose()`** - Automatic hardware and OpenCV checks
2. **`benchmark_first_frame()`** - Measure real startup time
3. **`wait_for_first_frame()` with logging** - Better error messages
4. **Diagnostic tool** - One-command analysis: `python camera_diagnostic.py`

Use these tools to identify the specific issue and apply the appropriate fix from above.
