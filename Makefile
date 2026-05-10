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
