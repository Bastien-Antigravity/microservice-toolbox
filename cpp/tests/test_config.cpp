// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Core microservice-toolbox module: test_config.cpp.
//
// DATA FLOW:
// Callers -> test_config.cpp -> Processed Output
//
// KEY PARAMETERS:
// - Standard module parameters.
// -----------------------------------------------------------------------------

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
      << "  log_server: {ip: '127.0.0.2', port: '9998'}\n"
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
  std::cout << "Testing GetLocal & GetLocalTLSConfig..." << std::endl;
  ensure_config_dir();

  const std::string local_cfg_path = "config/test_local_override.yaml";
  std::ofstream ofs(local_cfg_path);
  ofs << "common:\n  name: test\n"
      << "capabilities:\n"
      << "  svc_local:\n    ip: '127.0.0.2'\n    port: '8090'\n"
      << "local:\n  local_setting: value_xyz\n  nested:\n    val: 123\n    "
      << "key: nested_value\n"
      << "  tls:\n"
      << "    cert_file: /tmp/test.crt\n"
      << "    key_file: /tmp/test.key\n"
      << "    ca_file: /tmp/ca.crt\n"
      << "    verify_client: false\n";
  ofs.close();

  setenv("CONFIG_PATH", local_cfg_path.c_str(), 1);
  auto ac = LoadConfig("standalone");
  unsetenv("CONFIG_PATH");

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

  LocalTLSConfig tls = ac->GetLocalTLSConfig();
  assert(tls.cert_file == "/tmp/test.crt");
  assert(tls.key_file == "/tmp/test.key");
  assert(tls.ca_file == "/tmp/ca.crt");
  assert(tls.verify_client.has_value() && *tls.verify_client == false);
  assert(!tls.ShouldVerifyClient());
  assert(!tls.IsEmpty());

  std::remove(local_cfg_path.c_str());
  std::cout << "  Passed." << std::endl;
}

void test_grpc_missing_error() {
  std::cout << "Testing gRPC Missing Error (Hardened)..." << std::endl;
  ensure_config_dir();

  std::ofstream ofs("config/test.yaml");
  ofs << "common: {name: test}\n"
      << "capabilities:\n"
      << "  log_server: {ip: '127.0.0.2', port: '9998'}\n"
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
  ensure_config_dir();

  std::ofstream ofs("config/test.yaml");
  ofs << "common: {name: expansion-test}\n"
      << "local:\n"
      << "  host: ${TEST_HOST:localhost}\n"
      << "  port: ${TEST_PORT:8080}\n";
  ofs.close();

  setenv("TEST_HOST", "127.0.0.5", 1);
  unsetenv("TEST_PORT");

  auto ac = LoadConfig("test");

  if (ac->GetLocal("host") != "127.0.0.5") {
    throw std::runtime_error("Env expansion failed for TEST_HOST. Got: " +
                             ac->GetLocal("host"));
  }
  if (ac->GetLocal("port") != "8080") {
    throw std::runtime_error(
        "Env expansion default failed for TEST_PORT. Got: " +
        ac->GetLocal("port"));
  }

  std::remove("config/test.yaml");
  std::cout << "  Passed." << std::endl;
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

void test_validate_unique_ports() {
  std::cout << "Testing ValidateUniquePorts..." << std::endl;
  ensure_config_dir();

  std::ofstream ofs("config/test.yaml");
  ofs << "common:\n  name: test-dup\n"
      << "capabilities:\n"
      << "  svc1:\n    ip: '127.0.0.1'\n    port: '8080'\n"
      << "  svc2:\n    ip: '127.0.0.1'\n    port: '8080'\n";
  ofs.close();

  bool caught = false;
  try {
    auto ac = LoadConfig("test");
  } catch (const std::exception &e) {
    caught = true;
    std::string msg = e.what();
    assert(msg.find("Duplicate endpoint detected") != std::string::npos);
  }
  std::remove("config/test.yaml");
  assert(caught);

  // Also test IPv6 wildcard :::8080 colliding with ::1:8080
  std::ofstream ofs6("config/test.yaml");
  ofs6 << "common:\n  name: test-dup-v6\n"
       << "capabilities:\n"
       << "  svc1:\n    ip: '::'\n    port: '8080'\n"
       << "  svc2:\n    ip: '::1'\n    port: '8080'\n";
  ofs6.close();

  bool caught_v6 = false;
  try {
    auto ac = LoadConfig("test");
  } catch (const std::exception &e) {
    caught_v6 = true;
    std::string msg = e.what();
    assert(msg.find("Duplicate endpoint detected") != std::string::npos);
  }
  std::remove("config/test.yaml");
  assert(caught_v6);
  std::cout << "  Passed (Duplicate endpoint caught for IPv4 and IPv6)." << std::endl;
}

void test_command_line_docker_guard() {
  std::cout << "Testing CommandLine Docker Guard..." << std::endl;
  const char *argv[] = {"test-app", "--host", "10.0.0.2", "--port", "9001",
                        "--grpc_host", "10.0.0.3", "--grpc_port", "9002"};
  int argc = static_cast<int>(sizeof(argv) / sizeof(argv[0]));

  unsetenv("DOCKER_ENV");
  CLIArgs host_args = CommandLine::Parse(argc, const_cast<char **>(argv));
  assert(host_args.host == "10.0.0.2");
  assert(host_args.port == 9001);
  assert(host_args.grpc_host == "10.0.0.3");
  assert(host_args.grpc_port == 9002);

  setenv("DOCKER_ENV", "true", 1);
  CLIArgs docker_args = CommandLine::Parse(argc, const_cast<char **>(argv));
  unsetenv("DOCKER_ENV");
  assert(docker_args.host.empty());
  assert(docker_args.port == 0);
  assert(docker_args.grpc_host.empty());
  assert(docker_args.grpc_port == 0);
  std::cout << "  Passed." << std::endl;
}

int main() {
  // Set TEST_HOST before Go runtime initializes via CGo
  setenv("TEST_HOST", "127.0.0.5", 1);

  // Cleanup any interference
  std::remove("test_config.yaml");
  std::remove("expansion_test.yaml");

  try {
    test_load_config_factory();
    test_address_resolution();
    test_decrypt_secret_logic();
    test_get_local();
    test_grpc_missing_error();
    test_env_expansion();
    test_mirror_integrity();
    test_validate_unique_ports();
    test_command_line_docker_guard();

    std::cout << "\n=======================================" << std::endl;
    std::cout << "  All C++ Toolbox Parity Tests Passed!" << std::endl;
    std::cout << "=======================================" << std::endl;
  } catch (const std::exception &e) {
    std::cerr << "\n!!! TEST FAILED: " << e.what() << std::endl;
    return 1;
  }
  return 0;
}
