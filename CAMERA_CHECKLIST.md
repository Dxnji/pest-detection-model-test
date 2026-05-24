# Camera Issue - Action Checklist

## ✅ What Was Done
- [x] Added `CameraVersion` class with OpenCV/hardware checks
- [x] Added `CameraService.diagnose()` method
- [x] Added `CameraService.benchmark_first_frame()` method  
- [x] Enhanced `wait_for_first_frame()` with diagnostic logging
- [x] Created `camera_diagnostic.py` standalone tool
- [x] Created `test_camera_enhancements.py` test suite
- [x] Created comprehensive troubleshooting guides
- [x] All code verified for syntax errors

## 📋 Next Steps - Follow This Order

### Phase 1: Verify Installation (5 minutes)
- [ ] Run test suite: `python test_camera_enhancements.py`
  - Expected: "✓ ALL TESTS PASSED"
  - If fails: Report error to developer

### Phase 2: Diagnose Current Issue (2-3 minutes)
- [ ] Run quick diagnostic: `python camera_diagnostic.py --quick`
  - Read output carefully
  - Note any warnings or errors
  - Check "Recommendations" section

### Phase 3: Interpret Results
- [ ] Is camera found?
  - If NO: See "Camera not found" below
  - If YES: Continue

- [ ] What's the median latency?
  - < 0.5s: Good, probably no issue
  - 0.5-2s: Acceptable, optional optimization
  - 2-5s: Slow, optimize configs.py
  - > 5s: Very slow, needs fixes

### Phase 4: Apply Fix (based on issue)

#### If Camera Not Found:
```bash
# Step 1: Check hardware
ls -la /dev/video*

# Step 2: Check permissions
# If no read/write, run:
sudo usermod -a -G video $USER

# Step 3: Try different device
python camera_diagnostic.py --device=1
```

#### If Latency is High (> 2 seconds):
```python
# Edit configs.py - reduce resolution and FPS:

# Before:
INFERENCE_WIDTH = 320
INFERENCE_HEIGHT = 320
FRAME_SKIP = 4
TARGET_FPS = 15

# After:
INFERENCE_WIDTH = 160
INFERENCE_HEIGHT = 160
FRAME_SKIP = 8
TARGET_FPS = 10
```

Then re-run: `python camera_diagnostic.py --quick`

#### If Timeouts Still Happen:
```python
# Edit app.py - increase timeout

# Find this line (around line 281):
if not self.camera_service.wait_for_first_frame(timeout=5.0):

# Change to (use 1.5x measured latency):
if not self.camera_service.wait_for_first_frame(timeout=10.0):
```

### Phase 5: Verify Fix Works
- [ ] Run full diagnostic: `python camera_diagnostic.py`
  - Should show successful startup
  - Measure new latency
  - Note recommended timeout

- [ ] Test startup in robot:
  ```bash
  python app.py
  ```
  - Should see "First frame received" logs
  - Robot should reach READY state

## 📚 Reference Documents (by use case)

### Quick Start
- `CAMERA_QUICK_REF.md` - One-page reference

### Detailed Troubleshooting  
- `CAMERA_TROUBLESHOOTING.md` - 10+ fixes with examples

### Understand How It Works
- `CAMERA_SOLUTION.md` - Technical overview
- `CAMERA_ARCHITECTURE.md` - System design diagrams

### For Developers
- `services/camera_service.py` - Modified code
- Source: Check docstrings in code

## 🔧 Tools Available

### Diagnostic Tool
```bash
python camera_diagnostic.py                    # Full (2-3 min)
python camera_diagnostic.py --quick            # Quick (30 sec)
python camera_diagnostic.py --device=1         # Different camera
python camera_diagnostic.py --benchmark-trials=5  # More precision
```

### Test Suite
```bash
python test_camera_enhancements.py             # Verify features
```

### Direct API Use
```python
from services.camera_service import CameraService

cam = CameraService()

# Get recommendations
report = cam.diagnose()

# Measure real latency
latency = cam.benchmark_first_frame(trials=3)

# Start and wait with better logging
cam.start()
if cam.wait_for_first_frame(timeout=10.0):
    print("Success!")
else:
    print("Failed - check logs above")
cam.stop()
```

## ❓ Common Questions

**Q: How long should first frame take?**
A: 
- Good: < 500ms
- Acceptable: 500ms - 2s
- Slow: > 2s
Use diagnostic tool to measure yours.

**Q: What timeout should I use?**
A: 
1. Run: `python camera_diagnostic.py`
2. Find "Recommended Timeout: X.XXs"
3. Use that value in app.py

**Q: My camera is slow, how do I fix it?**
A:
1. Run diagnostic to confirm it's slow
2. Reduce INFERENCE_WIDTH/HEIGHT in configs.py
3. Re-run diagnostic to verify
4. See CAMERA_TROUBLESHOOTING.md for more

**Q: Camera works on my PC but not on RPi**
A:
1. Run diagnostic on both
2. Compare latencies
3. RPi may need lower resolution
4. Check power supply (most common issue)

**Q: Where do I find the logs?**
A:
- Real-time: Watch `app.py` output
- Files: Check `logs/` directory
- Search for "Camera" to find relevant lines

## 📞 Need More Help?

### Check These in Order:
1. `CAMERA_QUICK_REF.md` - Quick reference
2. `CAMERA_TROUBLESHOOTING.md` - Detailed fixes  
3. `CAMERA_SOLUTION.md` - Technical details
4. `CAMERA_ARCHITECTURE.md` - System design

### Still Stuck?
Run full diagnostics and save output:
```bash
python camera_diagnostic.py > camera_diagnostic_output.txt 2>&1
# Then review the output for error details
```

## 🎯 Success Criteria

You'll know it's fixed when:
- [ ] `python camera_diagnostic.py` completes without errors
- [ ] Shows "✓ Camera is accessible"
- [ ] Median latency is < 2 seconds
- [ ] `python app.py` reaches READY state
- [ ] Logs show "First frame captured" message

---

**Summary**: Run `python camera_diagnostic.py` to identify your specific issue, then apply the corresponding fix from this checklist.
