#!/usr/bin/env python3
"""Simple test to check if metrics generation works."""

import time
from prometheus_client import generate_latest

print("Testing prometheus_client directly...")
try:
    start = time.time()
    metrics = generate_latest()
    elapsed = time.time() - start
    
    print(f"✅ generate_latest() completed in {elapsed:.3f}s")
    print(f"Generated {len(metrics)} bytes of metrics data")
    print(f"First 500 chars:\n{metrics[:500].decode('utf-8')}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()