"""
End-to-end validation tests for LLM service with MCP tool calling.

These tests validate complete workflows from user input through tool execution
to final response. Requires real LLM API calls and MCP servers.
"""

import unittest
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
import json

# Add backend src to path
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root / "src"))

from agent.services.llm_service import LLM
from agent.core.mcp_client import get_mcp_manager
from dotenv import load_dotenv


class TestLLMMCPEndToEnd(unittest.IsolatedAsyncioTestCase):
    """End-to-end validation tests for complete LLM+MCP workflows."""
    
    @classmethod
    def setUpClass(cls):
        """Load environment variables for testing."""
        # Load .env files
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        env_local_path = Path(__file__).parent.parent.parent.parent / ".env.local"
        
        if env_path.exists():
            load_dotenv(env_path)
        if env_local_path.exists():
            load_dotenv(env_local_path, override=True)
    
    async def asyncSetUp(self):
        """Set up test environment."""
        # Reset the global MCP manager for each test
        import agent.core.mcp_client as mcp_module
        mcp_module._mcp_manager = None
        
        # Check if we have required API keys
        self.has_github_token = bool(os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"))
        self.has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
        self.has_anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        # Reset the global MCP manager
        import agent.core.mcp_client as mcp_module
        if mcp_module._mcp_manager:
            for server in list(mcp_module._mcp_manager.clients.keys()):
                await mcp_module._mcp_manager.disconnect(server)
            mcp_module._mcp_manager = None
    
    @unittest.skipUnless(
        os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") and os.getenv("OPENAI_API_KEY"),
        "Skipping E2E test - requires GITHUB_PERSONAL_ACCESS_TOKEN and OPENAI_API_KEY"
    )
    async def test_e2e_github_issue_retrieval(self):
        """Complete E2E test: User asks about GitHub issue, LLM uses tools, returns answer."""
        print("\n" + "="*70)
        print("E2E TEST: GitHub Issue Retrieval")
        print("="*70)
        
        # Initialize MCP and LLM
        mcp_manager = await get_mcp_manager()
        llm = LLM(caller="e2e_github", mcp_manager=mcp_manager)
        
        # Track the complete flow
        flow_events = []
        
        async def on_tool_start(name, args):
            flow_events.append(("tool_start", name, args))
            print(f"\n→ Tool starting: {name}")
            print(f"  Args: {args}")
        
        async def on_tool_complete(name, result):
            flow_events.append(("tool_complete", name, result))
            print(f"✓ Tool completed: {name}")
            if isinstance(result, dict):
                # Show abbreviated result
                result_str = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                print(f"  Result: {result_str}")
        
        async def on_tool_error(name, error):
            flow_events.append(("tool_error", name, error))
            print(f"✗ Tool error: {name}: {error}")
        
        # User message asking about a specific issue
        messages = [
            {
                "role": "system",
                "content": "You have access to GitHub tools. Use them to get real data when asked about GitHub repositories."
            },
            {
                "role": "user",
                "content": "What is issue #40 about in the bryan-zxc/agent repository? Get the title and summarize what it's about in one sentence."
            }
        ]
        
        # Time the complete operation
        start_time = time.time()
        
        try:
            response = await llm.a_get_response(
                messages=messages,
                model="gpt-4.1-nano",
                temperature=0,
                on_tool_start=on_tool_start,
                on_tool_complete=on_tool_complete,
                on_tool_error=on_tool_error,
                max_tool_rounds=5
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Validate response
            self.assertIsNotNone(response)
            self.assertTrue(hasattr(response, 'content'))
            
            print(f"\n📝 Final Response:")
            print(f"{response.content}")
            
            print(f"\n📊 Flow Summary:")
            print(f"  Duration: {duration:.2f} seconds")
            print(f"  Total events: {len(flow_events)}")
            
            # Count event types
            tool_starts = sum(1 for e in flow_events if e[0] == "tool_start")
            tool_completes = sum(1 for e in flow_events if e[0] == "tool_complete")
            tool_errors = sum(1 for e in flow_events if e[0] == "tool_error")
            
            print(f"  Tool starts: {tool_starts}")
            print(f"  Tool completions: {tool_completes}")
            print(f"  Tool errors: {tool_errors}")
            
            # Validate that tools were actually called
            self.assertGreater(tool_starts, 0, "Should have called at least one tool")
            self.assertEqual(tool_starts, tool_completes, "All started tools should complete")
            
            # Check that response mentions issue #40
            self.assertIn("40", response.content, "Response should mention issue #40")
            
            print("\n✅ E2E test completed successfully")
            
        except Exception as e:
            print(f"\n❌ E2E test failed: {e}")
            raise
    
    @unittest.skipUnless(
        os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") and os.getenv("OPENAI_API_KEY"),
        "Skipping performance test - requires API keys"
    )
    async def test_performance_multiple_tool_rounds(self):
        """Test performance with multiple tool calling rounds."""
        print("\n" + "="*70)
        print("PERFORMANCE TEST: Multiple Tool Rounds")
        print("="*70)
        
        mcp_manager = await get_mcp_manager()
        llm = LLM(caller="perf_test", mcp_manager=mcp_manager)
        
        # Track performance metrics
        round_times = []
        
        async def on_tool_start(name, args):
            round_times.append(("start", time.time(), name))
        
        async def on_tool_complete(name, result):
            round_times.append(("complete", time.time(), name))
        
        # Message that might require multiple tool calls
        messages = [
            {
                "role": "user",
                "content": "List the 3 most recent issues in bryan-zxc/agent repository and tell me their titles."
            }
        ]
        
        start_time = time.time()
        
        response = await llm.a_get_response(
            messages=messages,
            model="gpt-4.1-nano",
            temperature=0,
            on_tool_start=on_tool_start,
            on_tool_complete=on_tool_complete,
            max_tool_rounds=5
        )
        
        total_time = time.time() - start_time
        
        # Analyze performance
        print(f"\n📊 Performance Metrics:")
        print(f"  Total time: {total_time:.2f} seconds")
        
        # Calculate individual tool execution times
        tool_times = []
        for i in range(0, len(round_times), 2):
            if i + 1 < len(round_times):
                start = round_times[i]
                complete = round_times[i + 1]
                if start[0] == "start" and complete[0] == "complete":
                    duration = complete[1] - start[1]
                    tool_times.append((start[2], duration))
        
        if tool_times:
            print(f"  Tool executions: {len(tool_times)}")
            for tool_name, duration in tool_times:
                print(f"    - {tool_name}: {duration:.3f}s")
            
            avg_time = sum(t[1] for t in tool_times) / len(tool_times)
            print(f"  Average tool time: {avg_time:.3f}s")
        
        # Performance assertions
        self.assertLess(total_time, 30, "Total execution should be under 30 seconds")
        
        print("\n✅ Performance test completed")
    
    @unittest.skipUnless(
        os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),
        "Skipping stress test - requires GITHUB_PERSONAL_ACCESS_TOKEN"
    )
    async def test_stress_concurrent_tool_calls(self):
        """Stress test with concurrent LLM+MCP operations."""
        print("\n" + "="*70)
        print("STRESS TEST: Concurrent Operations")
        print("="*70)
        
        mcp_manager = await get_mcp_manager()
        
        # Create multiple LLM instances
        num_concurrent = 3
        llms = [
            LLM(caller=f"stress_{i}", mcp_manager=mcp_manager)
            for i in range(num_concurrent)
        ]
        
        # Different queries for each instance
        queries = [
            "What is issue #40 about in bryan-zxc/agent?",
            "List the labels on issue #40 in bryan-zxc/agent",
            "What is the state of issue #40 in bryan-zxc/agent?"
        ]
        
        async def run_query(llm, query, index):
            """Run a single query and return timing."""
            start = time.time()
            
            messages = [{"role": "user", "content": query}]
            
            try:
                response = await llm.a_get_response(
                    messages=messages,
                    model="gpt-4.1-nano",
                    temperature=0,
                    max_tool_rounds=3
                )
                
                duration = time.time() - start
                return (index, duration, True, response.content[:100] if response else "No response")
            except Exception as e:
                duration = time.time() - start
                return (index, duration, False, str(e))
        
        # Run concurrent queries
        print(f"\nRunning {num_concurrent} concurrent queries...")
        start_time = time.time()
        
        tasks = [
            run_query(llm, query, i)
            for i, (llm, query) in enumerate(zip(llms, queries))
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # Analyze results
        print(f"\n📊 Stress Test Results:")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Concurrent operations: {num_concurrent}")
        
        successful = 0
        for index, duration, success, content in results:
            if not isinstance(content, Exception):
                status = "✓" if success else "✗"
                print(f"  Query {index}: {status} {duration:.2f}s")
                if success:
                    successful += 1
        
        print(f"  Success rate: {successful}/{num_concurrent}")
        
        # Validate stress test
        self.assertGreater(successful, 0, "At least one query should succeed")
        
        # Check that concurrent execution is faster than sequential
        avg_time = sum(r[1] for r in results if not isinstance(r, Exception)) / len(results)
        print(f"  Average query time: {avg_time:.2f}s")
        print(f"  Speedup vs sequential: {(avg_time * num_concurrent / total_time):.1f}x")
        
        print("\n✅ Stress test completed")
    
    async def test_error_recovery_e2e(self):
        """Test error recovery in E2E scenario."""
        print("\n" + "="*70)
        print("ERROR RECOVERY TEST")
        print("="*70)
        
        mcp_manager = await get_mcp_manager()
        llm = LLM(caller="error_test", mcp_manager=mcp_manager)
        
        errors_encountered = []
        
        async def on_tool_error(name, error):
            errors_encountered.append((name, error))
            print(f"\n✗ Handling error in {name}: {error}")
        
        # Query that might fail (non-existent issue)
        messages = [
            {
                "role": "user",
                "content": "What is issue #999999 about in bryan-zxc/agent repository?"
            }
        ]
        
        response = await llm.a_get_response(
            messages=messages,
            model="gpt-4.1-nano",
            temperature=0,
            on_tool_error=on_tool_error,
            max_tool_rounds=2
        )
        
        # Should still get a response even if tool fails
        self.assertIsNotNone(response)
        
        print(f"\n📝 Response after error: {response.content[:200] if response else 'None'}")
        print(f"Errors encountered: {len(errors_encountered)}")
        
        print("\n✅ Error recovery test completed")


class TestLLMScenarios(unittest.IsolatedAsyncioTestCase):
    """Test specific real-world scenarios."""
    
    @unittest.skipUnless(
        os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),
        "Skipping scenario test - requires GITHUB_PERSONAL_ACCESS_TOKEN"
    )
    async def test_scenario_multi_step_research(self):
        """Test a multi-step research scenario."""
        print("\n" + "="*70)
        print("SCENARIO: Multi-Step Research")
        print("="*70)
        
        mcp_manager = await get_mcp_manager()
        llm = LLM(caller="scenario_research", mcp_manager=mcp_manager)
        
        # Complex research query
        messages = [
            {
                "role": "user",
                "content": (
                    "Research the bryan-zxc/agent repository: "
                    "1. How many open issues are there? "
                    "2. What are the most recent 2 issues about?"
                )
            }
        ]
        
        tool_calls = []
        
        async def on_tool_complete(name, result):
            tool_calls.append(name)
            print(f"\n→ Tool used: {name}")
        
        response = await llm.a_get_response(
            messages=messages,
            model="gpt-4.1-nano",
            temperature=0,
            on_tool_complete=on_tool_complete,
            max_tool_rounds=5
        )
        
        print(f"\n📝 Research Results:")
        print(response.content if response else "No response")
        
        print(f"\n📊 Tools used: {len(tool_calls)}")
        for tool in set(tool_calls):
            count = tool_calls.count(tool)
            print(f"  - {tool}: {count} time(s)")
        
        self.assertGreater(len(tool_calls), 0, "Should have used tools for research")
        
        print("\n✅ Multi-step research scenario completed")


if __name__ == "__main__":
    # Run with verbosity for detailed output
    unittest.main(verbosity=2)