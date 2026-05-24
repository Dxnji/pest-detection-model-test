#!/usr/bin/env python3
"""
Quick test to verify camera diagnostic features work.
Does NOT require actual camera hardware.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.camera_service import CameraVersion

def test_version_checks():
    """Test version checking without camera hardware."""
    print("Testing CameraVersion class...")
    
    version_str = CameraVersion.get_opencv_version()
    print(f"  OpenCV version: {version_str}")
    assert version_str, "Failed to get OpenCV version"
    
    major, minor = CameraVersion.get_opencv_major_minor()
    print(f"  Major.Minor: {major}.{minor}")
    assert major > 0, "Invalid OpenCV major version"
    
    # v4l2 check won't work without camera, but shouldn't crash
    try:
        v4l2 = CameraVersion.check_v4l2_support()
        print(f"  v4l2 backend: {v4l2}")
    except Exception as e:
        print(f"  v4l2 check failed (expected without camera): {e}")
    
    print("✓ Version checks passed\n")

def test_camera_service_methods():
    """Test that new methods exist."""
    print("Testing CameraService new methods...")
    from services.camera_service import CameraService
    
    cam = CameraService()
    
    # Check methods exist
    assert hasattr(cam, 'diagnose'), "Missing diagnose() method"
    assert hasattr(cam, 'benchmark_first_frame'), "Missing benchmark_first_frame() method"
    
    # Check diagnose() returns correct structure
    report = cam.diagnose()
    required_keys = ['opencv_version', 'camera_properties', 'recommendations']
    for key in required_keys:
        assert key in report, f"Missing key in diagnose(): {key}"
    
    print(f"  diagnose() returned: {list(report.keys())}")
    print(f"  OpenCV version: {report['opencv_version']}")
    print("✓ CameraService methods OK\n")

def test_wait_for_first_frame_logging():
    """Test that wait_for_first_frame logs properly."""
    print("Testing wait_for_first_frame() with timeout...")
    from services.camera_service import CameraService
    import time
    
    cam = CameraService()
    # Don't start the service, just test that wait times out gracefully
    start = time.time()
    result = cam.wait_for_first_frame(timeout=0.5)
    elapsed = time.time() - start
    
    assert result == False, "Expected timeout to return False"
    assert elapsed >= 0.4, "Timeout didn't wait long enough"
    print(f"  Timeout test passed ({elapsed:.2f}s elapsed)")
    print("✓ wait_for_first_frame() logging OK\n")

if __name__ == "__main__":
    print("=" * 60)
    print("CAMERA ENHANCEMENT TESTS")
    print("=" * 60 + "\n")
    
    try:
        test_version_checks()
        test_camera_service_methods()
        test_wait_for_first_frame_logging()
        
        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Run: python camera_diagnostic.py")
        print("  2. Check the CAMERA_TROUBLESHOOTING.md guide")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
