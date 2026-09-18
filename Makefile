VERSION := $(shell cat VERSION.txt 2>/dev/null || echo "0.0.1")

.PHONY: all build test version clean

all: build

version:
	@echo $(VERSION)

build:
	@echo "Building repository (version $(VERSION))..."
	@if [ -f "go.mod" ]; then go build ./go/...; fi
	@if [ -f "rust/Cargo.toml" ]; then (cd rust && cargo build --release); fi
	@if [ -f "cpp/Makefile" ]; then $(MAKE) -C cpp all; fi

test:
	@echo "Running tests (version $(VERSION))..."
	@if [ -f "go.mod" ]; then go test ./go/...; fi
	@if [ -f "rust/Cargo.toml" ]; then (cd rust && cargo test); fi
	@if [ -f "python/pyproject.toml" ]; then pytest python/; fi
	@if [ -f "cpp/Makefile" ]; then $(MAKE) -C cpp test; fi

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf dist build *.egg-info bin/
	@if [ -f "cpp/Makefile" ]; then $(MAKE) -C cpp clean; fi

