#!/bin/bash
set -e

# Configuration
PROFILE="standalone"
YAML_FILE="integration/expansion_test.yaml"

echo ">>> BUILDING INTEGRATION UTILITIES <<<"
(cd go && go build -o ../bin/go_expansion_check ../integration/expansion_check.go)
(cd rust && cargo build --bin expansion_check --quiet && cp target/debug/expansion_check ../bin/rust_expansion_check)
(cd cpp && make bin/expansion_check --quiet && cp bin/expansion_check ../bin/cpp_expansion_check)

# Cleanup on exit
trap 'rm -f standalone.yaml go/standalone.yaml rust/standalone.yaml cpp/standalone.yaml' EXIT

# Copy test file to profile locations
cp $YAML_FILE standalone.yaml
cp $YAML_FILE go/standalone.yaml
cp $YAML_FILE rust/standalone.yaml
cp $YAML_FILE cpp/standalone.yaml

echo ">>> RUNNING YAML EXPANSION PARITY TEST (Go, Python, Rust, C++) <<<"

get_val() {
    local lang=$1
    local key=$2
    case $lang in
        go)
            ./bin/go_expansion_check $PROFILE "$key" | grep -o 'VALUE:.*' | cut -d: -f2
            ;;
        py)
            PYTHONPATH=python python3 integration/expansion_check.py $PROFILE "$key" | grep -o 'VALUE:.*' | cut -d: -f2
            ;;
        rust)
            ./bin/rust_expansion_check $PROFILE "$key" | grep -o 'VALUE:.*' | cut -d: -f2
            ;;
        cpp)
            ./bin/cpp_expansion_check $PROFILE "$key" | grep -o 'VALUE:.*' | cut -d: -f2
            ;;
    esac
}

# Test Case 1: Use Defaults
unset VAR_A
unset VAR_B
unset VAR_C

echo "Case 1: Defaults"
GO_VAL=$(get_val "go" "with_default")
PY_VAL=$(get_val "py" "with_default")
RS_VAL=$(get_val "rust" "with_default")
CPP_VAL=$(get_val "cpp" "with_default")

echo "  Go: $GO_VAL"
echo "  Python: $PY_VAL"
echo "  Rust: $RS_VAL"
echo "  C++: $CPP_VAL"

if [ "$GO_VAL" != "default_abc" ] || [ "$PY_VAL" != "default_abc" ] || [ "$RS_VAL" != "default_abc" ] || [ "$CPP_VAL" != "default_abc" ]; then
    echo "!!! PARITY FAILURE in Case 1 !!!"
    exit 1
fi

# Test Case 2: Environment Overrides
export VAR_A="overridden_val"
export VAR_C="nested_overridden"

echo "Case 2: Overrides"
GO_VAL=$(get_val "go" "with_default")
PY_VAL=$(get_val "py" "with_default")
RS_VAL=$(get_val "rust" "with_default")
CPP_VAL=$(get_val "cpp" "with_default")

GO_NESTED=$(get_val "go" "nested.val")
PY_NESTED=$(get_val "py" "nested.val")
RS_NESTED=$(get_val "rust" "nested.val")
CPP_NESTED=$(get_val "cpp" "nested.val")

echo "  Go (A): $GO_VAL, (C): $GO_NESTED"
echo "  Python (A): $PY_VAL, (C): $PY_NESTED"
echo "  Rust (A): $RS_VAL, (C): $RS_NESTED"
echo "  C++ (A): $CPP_VAL, (C): $CPP_NESTED"

if [ "$GO_VAL" != "overridden_val" ] || [ "$PY_VAL" != "overridden_val" ] || [ "$RS_VAL" != "overridden_val" ] || [ "$CPP_VAL" != "overridden_val" ]; then
    echo "!!! PARITY FAILURE in Case 2 (A) !!!"
    exit 1
fi

if [ "$GO_NESTED" != "nested_overridden" ] || [ "$PY_NESTED" != "nested_overridden" ] || [ "$RS_NESTED" != "nested_overridden" ] || [ "$CPP_NESTED" != "nested_overridden" ]; then
    echo "!!! PARITY FAILURE in Case 2 (C) !!!"
    exit 1
fi

echo ">>> YAML EXPANSION PARITY PASSED FOR ALL LANGUAGES! <<<"
