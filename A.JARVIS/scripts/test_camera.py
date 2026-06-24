import cv2
import time
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from security.camera import get_camera, get_detected_user

def test_camera():
    print("Initializing Camera...")
    cam = get_camera()
    
    print("Waiting for camera to warm up...")
    time.sleep(2)
    
    print("Testing frame capture...")
    frame = cam.get_display_frame()
    if frame is not None:
        print(f"Success! Captured frame of shape {frame.shape}")
        # Save a sample frame to verify visually
        cv2.imwrite('test_frame.jpg', frame)
        print("Sample frame saved as 'test_frame.jpg'")
    else:
        print("Failed to capture frame!")
        return

    print("Running for 5 seconds to test recognition...")
    start_time = time.time()
    while time.time() - start_time < 5:
        user = get_detected_user()
        if user:
            print(f"Detected user: {user}")
        time.sleep(1)

    print("Test complete. Releasing camera...")
    cam.is_running = False
    cam.video.release()

if __name__ == "__main__":
    test_camera()
