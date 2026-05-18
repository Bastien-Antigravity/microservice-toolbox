GOCMD=go
GOTEST=$(GOCMD) test

.PHONY: all clean test

all: build

build:
	cd go && $(GOCMD) build ./...

clean:
	rm -rf bin/

test:
	cd go && $(GOTEST) -v ./...
	cd cpp && make test

build-lib:
	@if [ ! -d "../distributed-config" ]; then \
		git clone -b develop https://github.com/Bastien-Antigravity/distributed-config.git ../distributed-config; \
	fi
	cd ../distributed-config && $(MAKE) build-lib

