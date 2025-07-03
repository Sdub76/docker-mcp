#!/usr/bin/env python3
"""
Simple test script to verify our Docker MCP changes work.
This tests the context support and basic functionality.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from docker_mcp.handlers import get_docker_client, DockerHandlers

async def test_context_support():
    """Test that context support works without breaking existing functionality."""
    print("Testing Docker context support...")
    
    # Test 1: Default behavior (should work as before)
    try:
        client = get_docker_client()
        print("✅ Default Docker client creation works")
    except Exception as e:
        print(f"❌ Default client failed: {e}")
        return False
    
    # Test 2: With DOCKER_HOST environment variable
    try:
        os.environ['DOCKER_HOST'] = 'unix:///var/run/docker.sock'  # Standard socket
        client_with_host = get_docker_client()
        print("✅ DOCKER_HOST environment variable support works")
        del os.environ['DOCKER_HOST']  # Clean up
    except Exception as e:
        print(f"❌ DOCKER_HOST support failed: {e}")
        return False
    
    # Test 3: With DOCKER_CONTEXT environment variable
    try:
        os.environ['DOCKER_CONTEXT'] = 'default'
        client_with_context = get_docker_client()
        print("✅ DOCKER_CONTEXT environment variable support works")
        del os.environ['DOCKER_CONTEXT']  # Clean up
    except Exception as e:
        print(f"❌ DOCKER_CONTEXT support failed: {e}")
        return False
    
    return True

async def test_enhanced_list_containers():
    """Test the enhanced list-containers functionality."""
    print("\nTesting enhanced list-containers...")
    
    try:
        result = await DockerHandlers.handle_list_containers({})
        print("✅ Enhanced list-containers works")
        print(f"Sample output: {result[0].text[:100]}...")
        return True
    except Exception as e:
        print(f"❌ Enhanced list-containers failed: {e}")
        return False

async def test_new_stats_tool():
    """Test the new get-container-stats tool."""
    print("\nTesting new get-container-stats tool...")
    
    try:
        # Test with a non-existent container (should handle gracefully)
        result = await DockerHandlers.handle_get_container_stats({"container_name": "non-existent-container"})
        print("✅ get-container-stats handles non-existent containers gracefully")
        return True
    except Exception as e:
        print(f"❌ get-container-stats failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🐳 Testing Docker MCP enhancements...\n")
    
    tests = [
        test_context_support(),
        test_enhanced_list_containers(),
        test_new_stats_tool()
    ]
    
    results = await asyncio.gather(*tests, return_exceptions=True)
    
    success_count = sum(1 for result in results if result is True)
    total_tests = len(results)
    
    print(f"\n📊 Test Results: {success_count}/{total_tests} passed")
    
    if success_count == total_tests:
        print("🎉 All tests passed! Changes are working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
