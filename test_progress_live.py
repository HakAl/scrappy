"""Quick test of LiveProgressReporter behavior."""
import time
import sys
sys.path.insert(0, 'src')

from infrastructure.progress import LiveProgressReporter

print("Starting LiveProgressReporter test...")
print("Watch for transient progress display\n")

progress = LiveProgressReporter()

# Test 1: Basic start/update/complete
print("Test 1: Basic progress flow")
progress.start("Testing progress display")
time.sleep(1)

progress.update(description="Update 1: Doing something")
time.sleep(1)

progress.update(description="Update 2: Still working")
time.sleep(1)

progress.complete("All done!")
time.sleep(0.5)  # Give time to see completion before it disappears

print("\nTest 1 complete - progress should have disappeared\n")
time.sleep(1)

# Test 2: Error handling
print("Test 2: Error display")
progress2 = LiveProgressReporter()
progress2.start("Testing error handling")
time.sleep(1)

progress2.error("Something went wrong!")
time.sleep(1.5)  # Give time to see error before it disappears

print("\nTest 2 complete - error should have disappeared\n")
time.sleep(1)

print("All tests complete!")
print("Type something here to test input interference: ", end="", flush=True)
