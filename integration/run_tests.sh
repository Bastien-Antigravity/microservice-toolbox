#!/bin/bash
set -e

# Configuration
TEMP_FILE="integration_data.bin"
FORMATS=("json" "msgpack")
LANGS=("go" "python" "rust")

# Helper to run generator
run_gen() {
    local lang=$1
    local format=$2
    if [ "$lang" == "go" ]; then
        cd go && go run ../integration/matrix_gen.go "$format" > "../integration/$TEMP_FILE" && cd ..
    elif [ "$lang" == "python" ]; then
        PYTHONPATH=python python3 integration/matrix_gen.py "$format" > "integration/$TEMP_FILE"
    elif [ "$lang" == "rust" ]; then
        cd rust && cargo run --quiet --bin integration_gen -- "$format" > "../integration/$TEMP_FILE" && cd ..
    fi
}

# Helper to run consumer
run_con() {
    local lang=$1
    local format=$2
    if [ "$lang" == "go" ]; then
        cd go && go run ../integration/matrix_con.go "$format" < "../integration/$TEMP_FILE" && cd ..
    elif [ "$lang" == "python" ]; then
        PYTHONPATH=python python3 integration/matrix_con.py "$format" < "integration/$TEMP_FILE"
    elif [ "$lang" == "rust" ]; then
        cd rust && cargo run --quiet --bin integration_con -- "$format" < "../integration/$TEMP_FILE" && cd ..
    fi
}

echo ">>> Starting Polyglot Integration Matrix Test..."

for format in "${FORMATS[@]}"; do
    for src in "${LANGS[@]}"; do
        for dst in "${LANGS[@]}"; do
            echo "Testing: $src -> $dst ($format)"
            run_gen "$src" "$format"
            run_con "$dst" "$format"
        done
    done
done

echo ">>> ALL INTEGRATION MATRIX TESTS PASSED! <<<"
rm -f integration/$TEMP_FILE
