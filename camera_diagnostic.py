#!/usr/bin/env python3
"""
Camera Diagnostic Tool

Helps troubleshoot camera startup issues by:
1. Checking OpenCV version and capabilities
2. Testing camera hardware availability
3. Benchmarking first-frame latency
4. Suggesting configuration optimizations

Usage:
    python camera_diagnostic.py              # Full diagnostic + benchmark
    python camera_diagnostic.py --quick      # Quick diagnostic only
    python camera_diagnostic.py --device=1   # Check /dev/video1
"""

import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.camera_service import CameraService, CameraConfig, CameraVersion
import configs

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def print_header(text: str) -> None:
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Camera diagnostic tool")
    parser.add_argument("--quick", action="store_true", help="Skip benchmarking")
    parser.add_argument("--device", type=int, default=0, help="Camera device number")
    parser.add_argument("--benchmark-trials", type=int, default=3, help="Number of benchmark trials")
    args = parser.parse_args()
    
    print_header("PEST DETECTION ROBOT - CAMERA DIAGNOSTIC TOOL")
    
    # Step 1: OpenCV version info
    print_header("1. OPENCV INFORMATION")
    opencv_version = CameraVersion.get_opencv_version()
    major, minor = CameraVersion.get_opencv_major_minor()
    print(f"OpenCV Version: {opencv_version}")
    print(f"Major.Minor: {major}.{minor}")
    
    if major < 4 or (major == 4 and minor < 5):
        print("⚠️  WARNING: OpenCV < 4.5 may have compatibility issues")
        print("   Consider upgrading: pip install --upgrade opencv-python-headless")
    else:
        print("✓ OpenCV version is acceptable")
    
    # Step 2: Backend check
    print_header("2. BACKEND CHECK")
    has_v4l2 = CameraVersion.check_v4l2_support()
    print(f"v4l2 Backend Available: {has_v4l2}")
    if has_v4l2:
        print("✓ v4l2 backend detected (good for RPi camera support)")
    else:
        print("⚠️  v4l2 backend not detected; camera may use fallback driver")
    
    # Step 3: Camera hardware check
    print_header("3. CAMERA HARDWARE CHECK")
    print(f"Testing device: /dev/video{args.device}")
    
    cam_config = CameraConfig(device=args.device)
    cam_service = CameraService(config=cam_config)
    
    diag_report = cam_service.diagnose()
    
    props = diag_report["camera_properties"]
    if props.get("error"):
        print(f"✗ FAILED: {props['error']}")
        print("\nSuggestions:")
        print("  1. Check that camera is connected: ls /dev/video*")
        print("  2. Check permissions: ls -la /dev/video*")
        print("  3. Try different device number: python camera_diagnostic.py --device=1")
        return 1
    
    print(f"✓ Camera is accessible")
    print(f"  Resolution: {props.get('width')}x{props.get('height')}")
    print(f"  FPS: {props.get('fps')}")
    print(f"  First Frame: {props.get('first_frame_time_ms'):.1f}ms")
    
    if diag_report["recommendations"]:
        print("\n⚠️  RECOMMENDATIONS:")
        for rec in diag_report["recommendations"]:
            print(f"  • {rec}")
    
    # Step 4: Benchmark (unless --quick)
    if not args.quick:
        print_header("4. FIRST-FRAME LATENCY BENCHMARK")
        print(f"Running {args.benchmark_trials} trials...\n")
        
        try:
            median_latency = cam_service.benchmark_first_frame(trials=args.benchmark_trials)
            
            print()
            print("BENCHMARK RESULTS:")
            print(f"  Median Latency: {median_latency:.2f}s")
            print(f"  Recommended Timeout: {median_latency * 1.5:.2f}s")
            
            if median_latency > 5:
                print("\n⚠️  SLOW STARTUP WARNING:")
                print("  First frame takes > 5 seconds!")
                print("  Suggestions:")
                print("    - Lower INFERENCE_HEIGHT/WIDTH in configs.py")
                print("    - Reduce TARGET_FPS in configs.py")
                print("    - Use lower-resolution camera input")
                print("    - Check for competing processes: htop")
                print("    - Verify power supply (brown-out can slow RPi)")
            elif median_latency > 2:
                print("\n⚠️  STARTUP COULD BE FASTER:")
                print(f"  Currently takes {median_latency:.2f}s; consider optimizations")
            else:
                print("\n✓ Startup latency is acceptable")
        
        except Exception as exc:
            logger.exception("Benchmark failed: %s", exc)
            return 1
    
    # Step 5: Configuration summary
    print_header("5. CURRENT CONFIGURATION")
    print(f"Device: {configs.CAMERA_DEVICE}")
    print(f"Inference Size: {configs.INFERENCE_WIDTH}x{configs.INFERENCE_HEIGHT}")
    print(f"Frame Skip: {configs.FRAME_SKIP}")
    print(f"Target FPS: {configs.TARGET_FPS}")
    
    print_header("DIAGNOSTIC COMPLETE")
    print("✓ All checks passed!" if not diag_report["recommendations"] else "⚠️  Review recommendations above")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
