# Camera Diagnostic - Quick Reference Card

## One-Line Diagnosis
```bash
python camera_diagnostic.py
```

## What It Does (30-60 seconds)
- Checks OpenCV version
- Tests camera hardware availability  
- Measures first-frame latency
- Suggests configuration optimizations

## Interpret the Output

### ✓ Good Result
```
✓ Camera is accessible
  Resolution: 640x480
  Median Latency: 0.35s
  Recommended Timeout: 0.53s
```
→ Nothing to fix, camera is working!

### ✗ Camera Not Found  
```
✗ FAILED: Failed to open VideoCapture
```
→ Fix: Check permissions `sudo usermod -a -G video $USER`

### ⚠️ High Latency (> 2s)
```
Median Latency: 3.5s
Recommended Timeout: 5.25s
```
→ Fix: Reduce resolution in `configs.py`:
```python
INFERENCE_WIDTH = 160  # was 320
INFERENCE_HEIGHT = 160  # was 320
```

### ⚠️ Intermittent Timeouts
→ Fix: Increase timeout in `app.py`:
```python
if not self.camera_service.wait_for_first_frame(timeout=10.0):  # was 5.0
```

## Advanced Options

```bash
# Quick check (skip benchmarking)
python camera_diagnostic.py --quick

# Test different camera device
python camera_diagnostic.py --device=1

# Change number of benchmark trials  
python camera_diagnostic.py --benchmark-trials=5
```

## From Code

```python
# In your code, you can now call:
from services.camera_service import CameraService

cam = CameraService()

# Get diagnostics
report = cam.diagnose()
print(f"Recommendations: {report['recommendations']}")

# Benchmark actual latency
median_latency = cam.benchmark_first_frame(trials=3)
print(f"Use timeout >= {median_latency * 1.5:.2f}s")

# Better logging in wait_for_first_frame()
if cam.wait_for_first_frame(timeout=10.0):
    print("Camera ready!")
else:
    # Error logs will show WHY it failed
    print("Check logs above for specific issue")
```

## Troubleshooting Checklist

- [ ] Run `python camera_diagnostic.py`
- [ ] Check camera is connected: `ls /dev/video*`
- [ ] Check permissions: `ls -la /dev/video*`
- [ ] If slow, reduce resolution in `configs.py`
- [ ] If intermittent, increase timeout in `app.py`
- [ ] Verify power supply is adequate (5V 2.5A+)
- [ ] Check thermal: `vcgencmd measure_temp` (RPi)
- [ ] See `CAMERA_TROUBLESHOOTING.md` for more

## Common Latencies
- **Good**: < 500ms
- **Acceptable**: 500ms - 2s  
- **Slow**: 2s - 5s
- **Very Slow**: > 5s

Use `1.5 × measured_latency` as safe timeout.

---

**TL;DR**: Run `python camera_diagnostic.py` to fix camera timeout issues.
