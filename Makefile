VERSION := $(strip $(shell cat VERSION.txt 2>/dev/null))
$(if $(VERSION),,$(error VERSION.txt is missing or empty))

.PHONY: all build test verify-standalone version clean

all: build

version:
	@echo $(VERSION)

verify-standalone:
	@echo "Verifying standalone Go build & tests (GOWORK=off)..."
	GOWORK=off go build ./go/...
	GOWORK=off go test ./go/...

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

