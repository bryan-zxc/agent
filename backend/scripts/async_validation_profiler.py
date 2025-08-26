#!/usr/bin/env python
"""
Async Validation Performance Profiler

Comprehensive performance analysis tool for the multi-layer async validation system.
Measures and optimises execution times across all validation layers to maintain 
development workflow efficiency.

Usage:
    python scripts/async_validation_profiler.py --full-analysis
    python scripts/async_validation_profiler.py --layer static
    python scripts/async_validation_profiler.py --benchmark --iterations 10
"""

import argparse
import asyncio
import subprocess
import sys
import time
import json
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from contextlib import asynccontextmanager
import tempfile


@dataclass
class ValidationLayerMetrics:
    """Performance metrics for a validation layer."""
    layer_name: str
    execution_times: List[float]
    success_rate: float
    average_time: float
    median_time: float
    p95_time: float
    max_time: float
    issues_detected: int
    throughput_per_second: float


@dataclass
class ProfilerResults:
    """Complete profiler analysis results."""
    layer_metrics: Dict[str, ValidationLayerMetrics]
    total_validation_time: float
    bottleneck_layer: str
    optimization_recommendations: List[str]
    performance_regression_detected: bool
    timestamp: str


class AsyncValidationProfiler:
    """Performance profiler for async validation layers."""
    
    def __init__(self):
        self.backend_dir = Path(__file__).parent.parent
        self.test_dir = self.backend_dir / "tests"
        self.validation_baselines = {
            'static_analysis': 5.0,      # seconds
            'runtime_testing': 15.0,     # seconds  
            'integration_testing': 120.0, # seconds
            'end_to_end_validation': 180.0 # seconds
        }
        
    async def profile_static_analysis_layer(self, iterations: int = 5) -> ValidationLayerMetrics:
        """Profile static analysis tools (Ruff, MyPy) performance."""
        
        print(f"📊 Profiling static analysis layer ({iterations} iterations)...")
        execution_times = []
        issues_detected = 0
        successful_runs = 0
        
        # Create test files with various async patterns for analysis
        test_files = await self._create_async_test_files()
        
        for i in range(iterations):
            start_time = time.time()
            
            try:
                # Profile Ruff execution
                ruff_start = time.time()
                ruff_result = subprocess.run([
                    sys.executable, '-m', 'ruff', 'check',
                    str(test_files['async_patterns']),
                    '--select', 'ASYNC'
                ], capture_output=True, text=True)
                ruff_time = time.time() - ruff_start
                
                # Profile MyPy execution
                mypy_start = time.time()
                mypy_result = subprocess.run([
                    sys.executable, '-m', 'mypy',
                    str(test_files['type_checking']),
                    '--strict', '--no-error-summary'
                ], capture_output=True, text=True)
                mypy_time = time.time() - mypy_start
                
                total_time = time.time() - start_time
                execution_times.append(total_time)
                
                # Count issues detected
                if ruff_result.returncode != 0:
                    issues_detected += len([line for line in ruff_result.stdout.split('\n') 
                                          if 'ASYNC' in line])
                
                successful_runs += 1
                
                print(f"   Iteration {i+1}: {total_time:.3f}s (Ruff: {ruff_time:.3f}s, MyPy: {mypy_time:.3f}s)")
                
            except Exception as e:
                print(f"   Iteration {i+1}: Failed - {e}")
        
        # Clean up test files
        await self._cleanup_test_files(test_files)
        
        return ValidationLayerMetrics(
            layer_name='static_analysis',
            execution_times=execution_times,
            success_rate=successful_runs / iterations,
            average_time=statistics.mean(execution_times) if execution_times else 0,
            median_time=statistics.median(execution_times) if execution_times else 0,
            p95_time=self._calculate_percentile(execution_times, 95) if execution_times else 0,
            max_time=max(execution_times) if execution_times else 0,
            issues_detected=issues_detected,
            throughput_per_second=len(test_files) / statistics.mean(execution_times) if execution_times else 0
        )
    
    async def profile_runtime_testing_layer(self, iterations: int = 5) -> ValidationLayerMetrics:
        """Profile runtime async warning capture performance."""
        
        print(f"📊 Profiling runtime testing layer ({iterations} iterations)...")
        execution_times = []
        warnings_detected = 0
        successful_runs = 0
        
        for i in range(iterations):
            start_time = time.time()
            
            try:
                # Run unit tests with async warning capture
                test_result = subprocess.run([
                    sys.executable, '-m', 'pytest',
                    str(self.test_dir / 'unit' / 'test_async_validation.py'),
                    '-v', '--tb=short'
                ], capture_output=True, text=True)
                
                total_time = time.time() - start_time
                execution_times.append(total_time)
                
                # Count async warnings detected
                if 'warning' in test_result.stdout.lower():
                    warnings_detected += test_result.stdout.lower().count('async')
                
                successful_runs += 1
                
                print(f"   Iteration {i+1}: {total_time:.3f}s")
                
            except Exception as e:
                print(f"   Iteration {i+1}: Failed - {e}")
        
        return ValidationLayerMetrics(
            layer_name='runtime_testing',
            execution_times=execution_times,
            success_rate=successful_runs / iterations,
            average_time=statistics.mean(execution_times) if execution_times else 0,
            median_time=statistics.median(execution_times) if execution_times else 0,
            p95_time=self._calculate_percentile(execution_times, 95) if execution_times else 0,
            max_time=max(execution_times) if execution_times else 0,
            issues_detected=warnings_detected,
            throughput_per_second=1 / statistics.mean(execution_times) if execution_times else 0
        )
    
    async def profile_integration_testing_layer(self, iterations: int = 3) -> ValidationLayerMetrics:
        """Profile integration testing performance."""
        
        print(f"📊 Profiling integration testing layer ({iterations} iterations)...")
        execution_times = []
        tests_completed = 0
        successful_runs = 0
        
        # Select lightweight integration tests for profiling
        integration_tests = [
            'test_lightweight_async_flows.py',
            'test_agent_activation_e2e.py'
        ]
        
        for i in range(iterations):
            start_time = time.time()
            
            try:
                for test_file in integration_tests:
                    test_path = self.test_dir / 'integration' / test_file
                    if test_path.exists():
                        test_result = subprocess.run([
                            sys.executable, '-m', 'pytest',
                            str(test_path),
                            '-v', '--tb=short'
                        ], capture_output=True, text=True)
                        
                        if test_result.returncode == 0:
                            tests_completed += 1
                
                total_time = time.time() - start_time
                execution_times.append(total_time)
                successful_runs += 1
                
                print(f"   Iteration {i+1}: {total_time:.3f}s ({tests_completed} tests)")
                
            except Exception as e:
                print(f"   Iteration {i+1}: Failed - {e}")
        
        return ValidationLayerMetrics(
            layer_name='integration_testing',
            execution_times=execution_times,
            success_rate=successful_runs / iterations,
            average_time=statistics.mean(execution_times) if execution_times else 0,
            median_time=statistics.median(execution_times) if execution_times else 0,
            p95_time=self._calculate_percentile(execution_times, 95) if execution_times else 0,
            max_time=max(execution_times) if execution_times else 0,
            issues_detected=tests_completed,
            throughput_per_second=len(integration_tests) / statistics.mean(execution_times) if execution_times else 0
        )
    
    async def profile_end_to_end_validation(self, iterations: int = 2) -> ValidationLayerMetrics:
        """Profile complete end-to-end validation performance."""
        
        print(f"📊 Profiling end-to-end validation ({iterations} iterations)...")
        execution_times = []
        validations_completed = 0
        successful_runs = 0
        
        for i in range(iterations):
            start_time = time.time()
            
            try:
                # Run the comprehensive end-to-end validation test
                validation_test_path = self.test_dir / 'validation' / 'test_end_to_end_async_prevention.py'
                
                if validation_test_path.exists():
                    test_result = subprocess.run([
                        sys.executable, '-m', 'pytest',
                        str(validation_test_path),
                        '-v', '--tb=short'
                    ], capture_output=True, text=True)
                    
                    if test_result.returncode == 0:
                        validations_completed += 1
                
                total_time = time.time() - start_time
                execution_times.append(total_time)
                successful_runs += 1
                
                print(f"   Iteration {i+1}: {total_time:.3f}s")
                
            except Exception as e:
                print(f"   Iteration {i+1}: Failed - {e}")
        
        return ValidationLayerMetrics(
            layer_name='end_to_end_validation',
            execution_times=execution_times,
            success_rate=successful_runs / iterations,
            average_time=statistics.mean(execution_times) if execution_times else 0,
            median_time=statistics.median(execution_times) if execution_times else 0,
            p95_time=self._calculate_percentile(execution_times, 95) if execution_times else 0,
            max_time=max(execution_times) if execution_times else 0,
            issues_detected=validations_completed,
            throughput_per_second=1 / statistics.mean(execution_times) if execution_times else 0
        )
    
    async def run_comprehensive_analysis(self, iterations: int = 5) -> ProfilerResults:
        """Run comprehensive performance analysis of all validation layers."""
        
        print("🚀 Starting Comprehensive Async Validation Performance Analysis")
        print("=" * 70)
        
        start_time = time.time()
        layer_metrics = {}
        
        # Profile each validation layer
        layer_metrics['static_analysis'] = await self.profile_static_analysis_layer(iterations)
        layer_metrics['runtime_testing'] = await self.profile_runtime_testing_layer(iterations)
        layer_metrics['integration_testing'] = await self.profile_integration_testing_layer(max(iterations//2, 1))
        layer_metrics['end_to_end_validation'] = await self.profile_end_to_end_validation(max(iterations//3, 1))
        
        total_time = time.time() - start_time
        
        # Identify bottleneck layer
        bottleneck_layer = max(layer_metrics.keys(), 
                             key=lambda k: layer_metrics[k].average_time)
        
        # Generate optimization recommendations
        recommendations = self._generate_optimization_recommendations(layer_metrics)
        
        # Check for performance regressions
        regression_detected = self._check_performance_regression(layer_metrics)
        
        results = ProfilerResults(
            layer_metrics=layer_metrics,
            total_validation_time=total_time,
            bottleneck_layer=bottleneck_layer,
            optimization_recommendations=recommendations,
            performance_regression_detected=regression_detected,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S')
        )
        
        await self._print_analysis_report(results)
        return results
    
    async def _create_async_test_files(self) -> Dict[str, Path]:
        """Create temporary test files for profiling analysis."""
        
        temp_dir = Path(tempfile.mkdtemp())
        test_files = {}
        
        # File with async patterns for Ruff analysis
        async_patterns_content = '''
import time
import asyncio

async def blocking_function():
    """Contains blocking calls that Ruff should detect."""
    time.sleep(1)  # ASYNC251: time.sleep in async function
    
    with open("test.txt", "w") as f:  # ASYNC230: blocking file operation
        f.write("test")
    
    return "completed"

async def subprocess_issue():
    """Contains subprocess calls that Ruff should detect."""
    import subprocess
    result = subprocess.run(["echo", "test"])  # ASYNC220: subprocess in async
    return result

async def proper_async_function():
    """Properly written async function."""
    await asyncio.sleep(1)
    
    import aiofiles
    async with aiofiles.open("test.txt", "w") as f:
        await f.write("test")
    
    return "completed"
'''
        
        # File for MyPy type checking
        type_checking_content = '''
from typing import Awaitable

async def returns_coroutine() -> str:
    await asyncio.sleep(0.1)
    return "result"

async def missing_await_example():
    """Function with potential missing await for MyPy analysis."""
    # This might or might not be caught by MyPy depending on type hints
    result = returns_coroutine()  # Missing await?
    return len(str(result))

async def proper_await_example():
    """Properly awaited function."""
    result = await returns_coroutine()
    return len(result)
'''
        
        test_files['async_patterns'] = temp_dir / "async_patterns.py"
        test_files['async_patterns'].write_text(async_patterns_content)
        
        test_files['type_checking'] = temp_dir / "type_checking.py"
        test_files['type_checking'].write_text(type_checking_content)
        
        return test_files
    
    async def _cleanup_test_files(self, test_files: Dict[str, Path]):
        """Clean up temporary test files."""
        import shutil
        
        for file_path in test_files.values():
            try:
                if file_path.parent.exists():
                    shutil.rmtree(file_path.parent)
                break  # All files in same temp dir
            except Exception:
                pass
    
    def _calculate_percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile value from list of numbers."""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = (percentile / 100) * (len(sorted_values) - 1)
        
        if index.is_integer():
            return sorted_values[int(index)]
        else:
            lower_index = int(index)
            upper_index = lower_index + 1
            weight = index - lower_index
            return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight
    
    def _generate_optimization_recommendations(self, layer_metrics: Dict[str, ValidationLayerMetrics]) -> List[str]:
        """Generate optimization recommendations based on performance analysis."""
        
        recommendations = []
        
        for layer_name, metrics in layer_metrics.items():
            baseline = self.validation_baselines.get(layer_name, 0)
            
            if metrics.average_time > baseline:
                if layer_name == 'static_analysis':
                    recommendations.append(
                        f"Static analysis exceeds {baseline}s baseline ({metrics.average_time:.2f}s). "
                        "Consider: reducing file scope, optimising Ruff/MyPy configuration, "
                        "or implementing incremental analysis."
                    )
                elif layer_name == 'runtime_testing':
                    recommendations.append(
                        f"Runtime testing exceeds {baseline}s baseline ({metrics.average_time:.2f}s). "
                        "Consider: reducing test scope, optimising test fixtures, "
                        "or improving async warning capture efficiency."
                    )
                elif layer_name == 'integration_testing':
                    recommendations.append(
                        f"Integration testing exceeds {baseline}s baseline ({metrics.average_time:.2f}s). "
                        "Consider: parallelising tests, reducing test data size, "
                        "or optimising database operations."
                    )
                elif layer_name == 'end_to_end_validation':
                    recommendations.append(
                        f"End-to-end validation exceeds {baseline}s baseline ({metrics.average_time:.2f}s). "
                        "Consider: selective validation, caching results, "
                        "or splitting into separate validation phases."
                    )
            
            # Check for performance variability
            if len(metrics.execution_times) > 1:
                std_dev = statistics.stdev(metrics.execution_times)
                cv = std_dev / metrics.average_time if metrics.average_time > 0 else 0
                
                if cv > 0.3:  # High variability
                    recommendations.append(
                        f"{layer_name.title()} shows high performance variability (CV: {cv:.2f}). "
                        "Consider investigating system resource constraints or test environment consistency."
                    )
        
        if not recommendations:
            recommendations.append("All validation layers performing within acceptable parameters. No optimization needed.")
        
        return recommendations
    
    def _check_performance_regression(self, layer_metrics: Dict[str, ValidationLayerMetrics]) -> bool:
        """Check if any layer shows significant performance regression."""
        
        regression_threshold = 1.5  # 50% slower than baseline
        
        for layer_name, metrics in layer_metrics.items():
            baseline = self.validation_baselines.get(layer_name, 0)
            if baseline > 0 and metrics.average_time > baseline * regression_threshold:
                return True
        
        return False
    
    async def _print_analysis_report(self, results: ProfilerResults):
        """Print comprehensive analysis report."""
        
        print("\n" + "=" * 70)
        print("🎯 ASYNC VALIDATION PERFORMANCE ANALYSIS REPORT")
        print("=" * 70)
        print(f"Analysis completed at: {results.timestamp}")
        print(f"Total analysis time: {results.total_validation_time:.2f}s")
        
        print(f"\n📊 LAYER PERFORMANCE SUMMARY:")
        print("-" * 70)
        
        for layer_name, metrics in results.layer_metrics.items():
            status = "🟢" if metrics.average_time <= self.validation_baselines.get(layer_name, float('inf')) else "🟡"
            baseline = self.validation_baselines.get(layer_name, 0)
            
            print(f"{status} {layer_name.upper()}:")
            print(f"   Average: {metrics.average_time:.3f}s (baseline: {baseline:.1f}s)")
            print(f"   Median: {metrics.median_time:.3f}s, P95: {metrics.p95_time:.3f}s, Max: {metrics.max_time:.3f}s")
            print(f"   Success rate: {metrics.success_rate*100:.1f}%")
            print(f"   Issues detected: {metrics.issues_detected}")
            print(f"   Throughput: {metrics.throughput_per_second:.2f} ops/sec")
        
        print(f"\n🔍 BOTTLENECK ANALYSIS:")
        print(f"Slowest layer: {results.bottleneck_layer}")
        
        if results.performance_regression_detected:
            print(f"\n⚠️  PERFORMANCE REGRESSION DETECTED")
        else:
            print(f"\n✅ No performance regression detected")
        
        print(f"\n💡 OPTIMIZATION RECOMMENDATIONS:")
        for i, recommendation in enumerate(results.optimization_recommendations, 1):
            print(f"{i}. {recommendation}")
        
        print("\n" + "=" * 70)
    
    async def save_results(self, results: ProfilerResults, output_path: str):
        """Save analysis results to JSON file."""
        
        # Convert results to JSON-serializable format
        json_data = {
            'timestamp': results.timestamp,
            'total_validation_time': results.total_validation_time,
            'bottleneck_layer': results.bottleneck_layer,
            'performance_regression_detected': results.performance_regression_detected,
            'optimization_recommendations': results.optimization_recommendations,
            'layer_metrics': {}
        }
        
        for layer_name, metrics in results.layer_metrics.items():
            json_data['layer_metrics'][layer_name] = {
                'execution_times': metrics.execution_times,
                'success_rate': metrics.success_rate,
                'average_time': metrics.average_time,
                'median_time': metrics.median_time,
                'p95_time': metrics.p95_time,
                'max_time': metrics.max_time,
                'issues_detected': metrics.issues_detected,
                'throughput_per_second': metrics.throughput_per_second
            }
        
        with open(output_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        print(f"📁 Results saved to: {output_path}")


async def main():
    """Main entry point for async validation profiler."""
    
    parser = argparse.ArgumentParser(
        description="Async Validation Performance Profiler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/async_validation_profiler.py --full-analysis
  python scripts/async_validation_profiler.py --layer static --iterations 10
  python scripts/async_validation_profiler.py --benchmark --output results.json
        """
    )
    
    parser.add_argument('--full-analysis', action='store_true',
                       help='Run comprehensive analysis of all validation layers')
    parser.add_argument('--layer', choices=['static', 'runtime', 'integration', 'e2e'],
                       help='Profile specific validation layer only')
    parser.add_argument('--iterations', type=int, default=5,
                       help='Number of iterations for performance measurement')
    parser.add_argument('--benchmark', action='store_true',
                       help='Run benchmark mode with extended iterations')
    parser.add_argument('--output', type=str,
                       help='Save results to JSON file')
    
    args = parser.parse_args()
    
    profiler = AsyncValidationProfiler()
    
    try:
        if args.benchmark:
            iterations = args.iterations * 2
            print(f"🏁 Running benchmark mode with {iterations} iterations...")
            results = await profiler.run_comprehensive_analysis(iterations)
        elif args.layer:
            print(f"🎯 Profiling {args.layer} layer only...")
            if args.layer == 'static':
                metrics = await profiler.profile_static_analysis_layer(args.iterations)
            elif args.layer == 'runtime':
                metrics = await profiler.profile_runtime_testing_layer(args.iterations)
            elif args.layer == 'integration':
                metrics = await profiler.profile_integration_testing_layer(args.iterations)
            elif args.layer == 'e2e':
                metrics = await profiler.profile_end_to_end_validation(args.iterations)
            
            print(f"\n📊 {args.layer.upper()} LAYER RESULTS:")
            print(f"   Average time: {metrics.average_time:.3f}s")
            print(f"   Success rate: {metrics.success_rate*100:.1f}%")
            print(f"   Issues detected: {metrics.issues_detected}")
            return
        else:
            # Default: full analysis
            results = await profiler.run_comprehensive_analysis(args.iterations)
        
        if args.output and 'results' in locals():
            await profiler.save_results(results, args.output)
            
    except KeyboardInterrupt:
        print("\n🛑 Profiling interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"💥 Profiler error: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())