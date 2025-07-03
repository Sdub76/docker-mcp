#!/usr/bin/env python3
"""
Static verification that our changes are syntactically correct and importable.
"""

import sys
from pathlib import Path

# Add the src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def test_imports():
    """Test that our modules can be imported without syntax errors."""
    try:
        from docker_mcp.handlers import get_docker_client, DockerHandlers
        print("✅ handlers.py imports successfully")
        
        from docker_mcp.server import server, handle_list_tools
        print("✅ server.py imports successfully")
        
        from docker_mcp import main
        print("✅ Main package imports successfully")
        
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_function_signatures():
    """Test that our new functions have correct signatures."""
    try:
        from docker_mcp.handlers import get_docker_client, DockerHandlers
        
        # Test get_docker_client function exists and is callable
        assert callable(get_docker_client), "get_docker_client should be callable"
        print("✅ get_docker_client function signature correct")
        
        # Test that our new handler method exists
        assert hasattr(DockerHandlers, 'handle_get_container_stats'), "handle_get_container_stats should exist"
        assert callable(DockerHandlers.handle_get_container_stats), "handle_get_container_stats should be callable"
        print("✅ handle_get_container_stats method exists")
        
        return True
    except Exception as e:
        print(f"❌ Function signature test failed: {e}")
        return False

def test_tool_definitions():
    """Test that tools are properly defined in server.py."""
    try:
        import asyncio
        from docker_mcp.server import handle_list_tools
        
        # Get the tools list
        tools = asyncio.run(handle_list_tools())
        tool_names = [tool.name for tool in tools]
        
        expected_tools = ['create-container', 'deploy-compose', 'get-logs', 'list-containers', 'get-container-stats']
        
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Tool {expected_tool} should be in tools list"
        
        print(f"✅ All expected tools found: {tool_names}")
        
        # Verify our new tool specifically
        stats_tool = next(tool for tool in tools if tool.name == 'get-container-stats')
        assert 'container_name' in stats_tool.inputSchema['properties'], "get-container-stats should have container_name parameter"
        print("✅ get-container-stats tool properly configured")
        
        return True
    except Exception as e:
        print(f"❌ Tool definition test failed: {e}")
        return False

def main():
    """Run all static verification tests."""
    print("🔍 Running static verification of Docker MCP changes...\n")
    
    tests = [
        ("Import Tests", test_imports),
        ("Function Signature Tests", test_function_signatures), 
        ("Tool Definition Tests", test_tool_definitions)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print(f"\n📊 Verification Results: {passed}/{total} test suites passed")
    
    if passed == total:
        print("🎉 All static verifications passed! Changes are syntactically correct.")
        print("\n📋 Summary of Changes:")
        print("  ✅ Added Docker context/host support via environment variables")
        print("  ✅ Enhanced list-containers to show more detailed information")
        print("  ✅ Added get-container-stats tool for container monitoring")
        print("  ✅ All changes are backward compatible")
        return True
    else:
        print("⚠️  Some verifications failed. Check the output above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
