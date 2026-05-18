CXX = g++
DISTCONF_DIR ?= ../../distributed-config/distconf/libdistconf
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude -I$(DISTCONF_DIR)
LDFLAGS = -L$(DISTCONF_DIR) -ldistconf -Wl,-rpath,$(DISTCONF_DIR)

TEST_SRC = tests/test_config.cpp
TEST_BIN = bin/test_config
EXPANSION_BIN = bin/expansion_check

.PHONY: all clean test

all: $(TEST_BIN) $(EXPANSION_BIN)

$(TEST_BIN): $(TEST_SRC)
	mkdir -p bin
	$(CXX) $(CXXFLAGS) $(TEST_SRC) -o $(TEST_BIN) $(LDFLAGS)

$(EXPANSION_BIN): ../integration/expansion_check.cpp
	mkdir -p bin
	$(CXX) $(CXXFLAGS) ../integration/expansion_check.cpp -o $(EXPANSION_BIN) $(LDFLAGS)

test: $(TEST_BIN)
	TEST_HOST=127.0.0.5 ./$(TEST_BIN)


clean:
	rm -rf bin/
