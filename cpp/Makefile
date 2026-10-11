CXX = g++
DISTCONF_DIR ?= ../../distributed-config/distconf/libdistconf
NOTIF_DIR ?= ../../notif-server/notif/libnotif
CXXFLAGS = -std=c++17 -Wall -Wextra -Iinclude -I$(DISTCONF_DIR)
LDFLAGS = -L$(DISTCONF_DIR) -ldistconf -Wl,-rpath,$(DISTCONF_DIR)

TEST_SRC = tests/test_config.cpp
TEST_BIN = bin/test_config
MODULES_SRC = tests/test_modules.cpp
MODULES_BIN = bin/test_modules
NOTIF_SRC = tests/test_notification.cpp
NOTIF_BIN = bin/test_notification
EXPANSION_BIN = bin/expansion_check

.PHONY: all clean test

all: $(TEST_BIN) $(MODULES_BIN) $(NOTIF_BIN) $(EXPANSION_BIN)

$(TEST_BIN): $(TEST_SRC)
	mkdir -p bin
	$(CXX) $(CXXFLAGS) $(TEST_SRC) -o $(TEST_BIN) $(LDFLAGS)

$(MODULES_BIN): $(MODULES_SRC)
	mkdir -p bin
	$(CXX) $(CXXFLAGS) $(MODULES_SRC) -o $(MODULES_BIN)

$(NOTIF_BIN): $(NOTIF_SRC)
	mkdir -p bin
	$(CXX) $(CXXFLAGS) $(NOTIF_SRC) -o $(NOTIF_BIN) $(LDFLAGS)

$(EXPANSION_BIN): ../integration/expansion_check.cpp
	mkdir -p bin
	$(CXX) $(CXXFLAGS) ../integration/expansion_check.cpp -o $(EXPANSION_BIN) $(LDFLAGS)

test: $(TEST_BIN) $(MODULES_BIN) $(NOTIF_BIN)
	DYLD_LIBRARY_PATH="$(DISTCONF_DIR):$$DYLD_LIBRARY_PATH" TEST_HOST=127.0.0.5 ./$(TEST_BIN)
	./$(MODULES_BIN)
	DYLD_LIBRARY_PATH="$(DISTCONF_DIR):$(NOTIF_DIR):$$DYLD_LIBRARY_PATH" ./$(NOTIF_BIN)


clean:
	rm -rf bin/ config/
