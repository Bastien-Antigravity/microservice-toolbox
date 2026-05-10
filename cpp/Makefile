CXX = g++
DISTCONF_DIR ?= ../../distributed-config/distconf/libdistconf
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude -I$(DISTCONF_DIR)
LDFLAGS = -L$(DISTCONF_DIR) -ldistconf -Wl,-rpath,$(DISTCONF_DIR)

TEST_SRC = tests/test_config.cpp
TEST_BIN = bin/test_config

.PHONY: all clean test

all: $(TEST_BIN)

$(TEST_BIN): $(TEST_SRC)
	mkdir -p bin
	$(CXX) $(CXXFLAGS) $(TEST_SRC) -o $(TEST_BIN) $(LDFLAGS)

test: $(TEST_BIN)
	./$(TEST_BIN)

clean:
	rm -rf bin/
