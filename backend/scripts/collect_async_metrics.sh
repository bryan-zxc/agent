#!/bin/bash
"""
Async Validation Metrics Collection Script

Automated collection of async validation effectiveness and performance metrics.
Run this script regularly to track validation system health and success.

Usage:
    ./scripts/collect_async_metrics.sh
    ./scripts/collect_async_metrics.sh --full-analysis
    ./scripts/collect_async_metrics.sh --output-dir custom/path
"""

set -e  # Exit on any error

# Configuration
DEFAULT_OUTPUT_DIR="metrics/async_validation"
DATE=$(date +%Y%m%d_%H%M)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Parse command line arguments
OUTPUT_DIR="$DEFAULT_OUTPUT_DIR"
FULL_ANALYSIS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --full-analysis)
            FULL_ANALYSIS=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--full-analysis] [--output-dir DIR]"
            echo ""
            echo "Options:"
            echo "  --full-analysis    Run comprehensive analysis with extended benchmarks"
            echo "  --output-dir DIR   Specify custom output directory (default: metrics/async_validation)"
            echo "  -h, --help         Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "📊 Async Validation Metrics Collection"
echo "======================================"
echo "Timestamp: $TIMESTAMP"
echo "Output Directory: $OUTPUT_DIR"
echo "Full Analysis: $FULL_ANALYSIS"
echo ""

# Function to log with timestamp
log() {
    echo "[$( date '+%H:%M:%S' )] $1"
}

# Function to handle errors
handle_error() {
    log "❌ Error in $1: $2"
    echo "   Continuing with next metric collection..."
}

# 1. Performance Benchmarking
log "🚀 Collecting performance benchmarks..."
if $FULL_ANALYSIS; then
    if python scripts/async_validation_profiler.py --benchmark --output "$OUTPUT_DIR/performance_$DATE.json" 2>/dev/null; then
        log "✅ Performance benchmark completed"
    else
        handle_error "performance benchmarking" "profiler execution failed"
    fi
else
    if python scripts/async_validation_profiler.py --full-analysis --output "$OUTPUT_DIR/performance_$DATE.json" 2>/dev/null; then
        log "✅ Performance analysis completed"
    else
        handle_error "performance analysis" "profiler execution failed"
    fi
fi

# 2. End-to-End Validation Effectiveness  
log "🎯 Running end-to-end validation tests..."
if python -m pytest tests/validation/test_end_to_end_async_prevention.py -v --json-report --json-report-file="$OUTPUT_DIR/e2e_validation_$DATE.json" > "$OUTPUT_DIR/e2e_output_$DATE.txt" 2>&1; then
    log "✅ End-to-end validation completed"
else
    handle_error "end-to-end validation" "validation tests failed"
fi

# 3. Static Analysis Metrics
log "🔍 Collecting static analysis metrics..."
{
    echo "=== RUFF ASYNC ANALYSIS ===" 
    echo "Timestamp: $TIMESTAMP"
    echo ""
    
    if python -m ruff check src/agent/ --select ASYNC --output-format=text; then
        echo "✅ Ruff analysis completed successfully"
    else
        echo "⚠️ Ruff found async issues (this is expected for metrics collection)"
    fi
    
    echo ""
    echo "=== MYPY TYPE CHECKING ==="
    echo ""
    
    if python -m mypy src/agent/ --strict --no-error-summary; then
        echo "✅ MyPy analysis completed successfully"  
    else
        echo "⚠️ MyPy found type issues (may include async-related issues)"
    fi
    
} > "$OUTPUT_DIR/static_analysis_$DATE.txt" 2>&1

log "✅ Static analysis metrics collected"

# 4. Runtime Testing Metrics
log "🧪 Collecting runtime testing metrics..."
if python -m pytest tests/unit/test_async_validation.py -v --tb=short > "$OUTPUT_DIR/runtime_testing_$DATE.txt" 2>&1; then
    log "✅ Runtime testing metrics completed"
else
    handle_error "runtime testing" "async validation tests failed"
fi

# 5. Integration Testing Performance
log "🔄 Collecting integration testing metrics..."
if python tests/run_integration_tests.py --suite lightweight_async_flows > "$OUTPUT_DIR/integration_lightweight_$DATE.txt" 2>&1; then
    log "✅ Lightweight integration tests completed"
else
    handle_error "lightweight integration tests" "integration tests failed"
fi

if python tests/run_integration_tests.py --suite agent_activation_e2e > "$OUTPUT_DIR/integration_e2e_$DATE.txt" 2>&1; then
    log "✅ E2E integration tests completed"
else
    handle_error "E2E integration tests" "integration tests failed"
fi

# 6. Test Coverage Analysis
log "📈 Generating test coverage analysis..."
if python -m pytest tests/ --cov=src/agent --cov-report=json --cov-report=term > "$OUTPUT_DIR/coverage_$DATE.txt" 2>&1; then
    # Move the generated coverage.json to our metrics directory
    if [ -f coverage.json ]; then
        mv coverage.json "$OUTPUT_DIR/coverage_$DATE.json"
    fi
    log "✅ Coverage analysis completed"
else
    handle_error "coverage analysis" "coverage generation failed"
fi

# 7. Generate Summary Report
log "📋 Generating metrics summary report..."

cat > "$OUTPUT_DIR/summary_$DATE.md" << EOF
# Async Validation Metrics Summary

**Collection Date**: $TIMESTAMP  
**Analysis Type**: $(if $FULL_ANALYSIS; then echo "Full Analysis"; else echo "Standard Analysis"; fi)

## Files Generated

### Performance Analysis
- \`performance_$DATE.json\` - Comprehensive performance benchmarks
- Performance targets: Static <5s, Runtime <15s, Integration <120s

### Validation Effectiveness  
- \`e2e_validation_$DATE.json\` - End-to-end validation test results
- \`e2e_output_$DATE.txt\` - Detailed validation output

### Layer-Specific Metrics
- \`static_analysis_$DATE.txt\` - Ruff and MyPy analysis results
- \`runtime_testing_$DATE.txt\` - Async warning capture test results  
- \`integration_lightweight_$DATE.txt\` - Lightweight integration test performance
- \`integration_e2e_$DATE.txt\` - End-to-end integration test performance

### Coverage Analysis
- \`coverage_$DATE.json\` - Test coverage data (JSON format)
- \`coverage_$DATE.txt\` - Test coverage report (human readable)

## Quick Analysis Commands

\`\`\`bash
# View performance summary
cat $OUTPUT_DIR/performance_$DATE.json | jq '.optimization_recommendations'

# Check validation effectiveness
grep "layers_that_caught_bug" $OUTPUT_DIR/e2e_validation_$DATE.json

# Review static analysis issues
grep "ASYNC" $OUTPUT_DIR/static_analysis_$DATE.txt

# Check integration test timing
grep "seconds" $OUTPUT_DIR/integration_*_$DATE.txt
\`\`\`

## Success Criteria Check

- [ ] **Performance Targets**: All layers meet timing targets
- [ ] **Bug Prevention**: Multiple layers catch original bug type  
- [ ] **Coverage**: >90% test coverage of async execution paths
- [ ] **Validation**: All validation tests pass

## Next Steps

1. Review performance metrics for any regressions
2. Analyse validation effectiveness results
3. Check static analysis for new async pattern issues
4. Monitor integration test performance trends

---
*Generated by collect_async_metrics.sh*
EOF

log "✅ Summary report generated"

# 8. Performance Trend Analysis (if previous data exists)
log "📊 Checking for performance trends..."

PREVIOUS_PERFORMANCE=$(find "$OUTPUT_DIR" -name "performance_*.json" -not -name "performance_$DATE.json" | head -1)
if [ -n "$PREVIOUS_PERFORMANCE" ]; then
    log "📈 Found previous performance data: $(basename $PREVIOUS_PERFORMANCE)"
    
    # Create simple trend comparison
    {
        echo "# Performance Trend Analysis"
        echo ""
        echo "**Current**: performance_$DATE.json"
        echo "**Previous**: $(basename $PREVIOUS_PERFORMANCE)"
        echo ""
        echo "## Layer Performance Comparison"
        echo ""
        
        # Extract key metrics for comparison (requires jq)
        if command -v jq >/dev/null 2>&1; then
            echo "### Static Analysis"
            echo "- Previous: $(cat "$PREVIOUS_PERFORMANCE" | jq -r '.layer_metrics.static_analysis.average_time // "N/A"')s"
            echo "- Current: $(cat "$OUTPUT_DIR/performance_$DATE.json" | jq -r '.layer_metrics.static_analysis.average_time // "N/A"')s"
            echo ""
            echo "### Integration Testing"  
            echo "- Previous: $(cat "$PREVIOUS_PERFORMANCE" | jq -r '.layer_metrics.integration_testing.average_time // "N/A"')s"
            echo "- Current: $(cat "$OUTPUT_DIR/performance_$DATE.json" | jq -r '.layer_metrics.integration_testing.average_time // "N/A"')s"
            echo ""
        else
            echo "*Install jq for detailed performance comparison*"
        fi
    } > "$OUTPUT_DIR/performance_trend_$DATE.md"
    
    log "✅ Performance trend analysis generated"
else
    log "ℹ️  No previous performance data found (first run)"
fi

# 9. Final Summary
echo ""
echo "======================================"
log "🎉 Metrics collection completed!"
echo ""
echo "📁 Results Location: $OUTPUT_DIR"
echo "📊 Files Generated:"
ls -1 "$OUTPUT_DIR"/*"$DATE"* | sed 's/^/   - /'
echo ""
echo "🔍 Review Summary: $OUTPUT_DIR/summary_$DATE.md"
echo ""

# Check if we can provide quick insights
if command -v jq >/dev/null 2>&1; then
    if [ -f "$OUTPUT_DIR/performance_$DATE.json" ]; then
        echo "⚡ Quick Performance Insights:"
        
        BOTTLENECK=$(cat "$OUTPUT_DIR/performance_$DATE.json" | jq -r '.bottleneck_layer // "unknown"')
        REGRESSION=$(cat "$OUTPUT_DIR/performance_$DATE.json" | jq -r '.performance_regression_detected // false')
        
        echo "   - Bottleneck layer: $BOTTLENECK"
        echo "   - Performance regression: $REGRESSION"
        echo ""
    fi
fi

echo "💡 Use these files to track async validation success over time!"
echo "🔄 Run this script regularly (weekly/monthly) for trend analysis."
echo ""