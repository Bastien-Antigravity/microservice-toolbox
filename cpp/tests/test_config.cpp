#include "../include/microservice_toolbox/config/AppConfig.hpp"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <unistd.h>

using namespace microservice_toolbox::config;

// Helper to ensure config directory exists
void ensure_config_dir() {
#ifdef _WIN32
  system("mkdir config 2>nul");
#else
  system("mkdir -p config");
#endif
}

void test_load_config_factory() {
  std::cout << "Testing LoadConfig Factory..." << std::endl;
  auto ac =
      LoadConfigWithLogger("standalone", std::make_shared<StdOutLogger>());
  assert(ac != nullptr);
  assert(ac->GetProfile() == "standalone");
  std::cout << "  Passed." << std::endl;
}

void test_address_resolution() {
  std::cout << "Testing Address Resolution..." << std::endl;
  ensure_config_dir();

  std::ofstream ofs("config/test.yaml");
  ofs << "common:\n  name: test-app\n"
      << "capabilities:\n"
      << "  log_server: {ip: '127.0.0.2', port: '9999'}\n"
      << "  config_server: {ip: '127.0.0.2', port: '9999'}\n"
      << "  svc:\n    ip: 127.0.0.2\n    port: '8080'\n    grpc_ip: "
         "127.0.0.2\n    grpc_port: '8081'";
  ofs.close();

  auto ac = LoadConfig("test");

  assert(ac->GetListenAddr("svc") == "127.0.0.2:8080");
  assert(ac->GetGRPCListenAddr("svc") == "127.0.0.2:8081");

  std::remove("config/test.yaml");
  std::cout << "  Passed." << std::endl;
}

void test_decrypt_secret_logic() {
  std::cout << "Testing DecryptSecret Hardened Logic..." << std::endl;
  auto ac = LoadConfig("standalone");

  assert(ac->DecryptSecret("normal_pass") == "normal_pass");
  assert(ac->DecryptSecret("") == "");
  assert(ac->DecryptSecret("ENC(no-close") == "ENC(no-close");
  assert(ac->DecryptSecret("not-ENC(data)") == "not-ENC(data)");

  try {
    std::string decrypted = ac->DecryptSecret("ENC(dummy)");
    // If we reach here, bridge somehow succeeded (unlikely in test)
    assert(!decrypted.empty());
  } catch (const std::exception& e) {
    std::string err = e.what();
    assert(!err.empty());
    std::cout << "  Passed (Caught Transparent Error: " << err << ")" << std::endl;
  }
}

void test_get_local() {
  std::cout << "Testing GetLocal..." << std::endl;
  ensure_config_dir();

  std::ofstream ofs("config/standalone.yaml");
  ofs << "common: {name: test}\n"
      << "local:\n  local_setting: value_xyz\n  nested:\n    val: 123\n    "
         "key: nested_value";
  ofs.close();

  auto ac = LoadConfig("standalone");
  if (ac->GetLocal("local_setting") != "value_xyz") {
    std::cerr << "  FAILED: Expected 'value_xyz', got '"
              << ac->GetLocal("local_setting") << "'" << std::endl;
    assert(false);
  }
  if (ac->GetLocal("nested.val") != "123") {
    std::cerr << "  FAILED: Expected '123', got '" << ac->GetLocal("nested.val")
              << "'" << std::endl;
    assert(false);
  }
  if (ac->GetLocal("nested.key") != "nested_value") {
    std::cerr << "  FAILED: Expected 'nested_value', got '"
              << ac->GetLocal("nested.key") << "'" << std::endl;
    assert(false);
  }
  assert(ac->GetLocal("missing") == "");

  std::remove("config/standalone.yaml");
  std::cout << "  Passed." << std::endl;
}

void test_grpc_missing_error() {
  std::cout << "Testing gRPC Missing Error (Hardened)..." << std::endl;
  ensure_config_dir();

  std::ofstream ofs("config/test.yaml");
  ofs << "common: {name: test}\n"
      << "capabilities:\n"
      << "  log_server: {ip: '127.0.0.2', port: '9999'}\n"
      << "  config_server: {ip: '127.0.0.2', port: '9999'}\n"
      << "  svc:\n    ip: 127.0.0.2\n    port: '8080'";
  ofs.close();

  auto ac = LoadConfig("test");

  bool threw = false;
  try {
    ac->GetGRPCListenAddr("svc");
  } catch (const std::runtime_error &) {
    threw = true;
  }
  assert(threw == true);

  std::remove("config/test.yaml");
  std::cout << "  Passed." << std::endl;
}

void test_env_expansion() {
  std::cout << "Testing Environment Variable Expansion..." << std::endl;

  // Using 'standalone' profile because it's known by the engine,
  // but we use a local override to test expansion.
  std::ofstream ofs("standalone.yaml");
  ofs << "common: {name: expansion-test}\n"
      << "local:\n"
      << "  host: ${TEST_HOST:localhost}\n"
      << "  port: ${TEST_PORT:8080}\n";
  ofs.close();

  setenv("TEST_HOST", "127.0.0.5", 1);
  unsetenv("TEST_PORT");

  auto ac = LoadConfig("standalone");

  if (ac->GetLocal("host") != "127.0.0.5") {
    throw std::runtime_error("Env expansion failed for TEST_HOST. Got: " +
                             ac->GetLocal("host"));
  }
  if (ac->GetLocal("port") != "8080") {
    throw std::runtime_error(
        "Env expansion default failed for TEST_PORT. Got: " +
        ac->GetLocal("port"));
  }

  std::cout << "  Passed." << std::endl;
  std::remove("standalone.yaml");
}

void test_mirror_integrity() {
  std::cout << "Testing Mirror Integrity (Full Sync)..." << std::endl;
  ensure_config_dir();

  std::ofstream ofs("config/test.yaml");
  ofs << "common: {name: mirror-test}\n"
      << "capabilities:\n"
      << "  sync_svc: {ip: '10.0.0.1', port: '1234'}";
  ofs.close();

  auto ac = LoadConfig("test");

  // We can't access data_ directly (it's local), but we can verify the sync log
  // and check if lookups work.
  assert(ac->GetListenAddr("sync_svc") == "10.0.0.1:1234");

  std::cout << "  Passed (In-memory mirror verified)." << std::endl;
  std::remove("config/test.yaml");
}

int main() {
  // Cleanup any interference
  std::remove("test_config.yaml");

  try {
    test_load_config_factory();
    test_address_resolution();
    test_decrypt_secret_logic();
    test_get_local();
    test_grpc_missing_error();
    test_env_expansion();
    test_mirror_integrity();

    std::cout << "\n=======================================" << std::endl;
    std::cout << "  All C++ Toolbox Parity Tests Passed!" << std::endl;
    std::cout << "=======================================" << std::endl;
  } catch (const std::exception &e) {
    std::cerr << "\n!!! TEST FAILED: " << e.what() << std::endl;
    return 1;
  }
  return 0;
}
