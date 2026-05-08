#ifndef MICROSERVICE_TOOLBOX_COMMAND_LINE_HPP
#define MICROSERVICE_TOOLBOX_COMMAND_LINE_HPP

#include <iostream>
#include <map>
#include <string>
#include <vector>

namespace microservice_toolbox {
namespace config {

struct CLIArgs {
  std::string name;
  std::string host;
  int port = 0;
  std::string grpc_host;
  int grpc_port = 0;
  std::string conf;
  std::string log_level;
  std::string key;
  std::string profile;
  std::map<std::string, std::string> extras;
};

class CommandLine {
public:
  static CLIArgs Parse(int argc, char **argv,
                       const std::vector<std::string> &specific_flags = {}) {
    CLIArgs args;
    std::vector<std::string> v_argv;
    for (int i = 1; i < argc; ++i) {
      v_argv.push_back(argv[i]);
    }

    for (size_t i = 0; i < v_argv.size(); ++i) {
      const std::string &arg = v_argv[i];

      if (arg == "--help" || arg == "-h") {
        PrintHelp(argv[0], specific_flags);
        exit(0);
      }

      auto parse_str = [&](const std::string &flag, std::string &target) {
        if (arg == flag && i + 1 < v_argv.size()) {
          target = v_argv[++i];
          return true;
        }
        if (arg.compare(0, flag.size() + 1, flag + "=") == 0) {
          target = arg.substr(flag.size() + 1);
          return true;
        }
        return false;
      };

      auto parse_int = [&](const std::string &flag, int &target) {
        std::string val;
        if (parse_str(flag, val)) {
          try {
            target = std::stoi(val);
          } catch (...) {
          }
          return true;
        }
        return false;
      };

      if (parse_str("--name", args.name))
        continue;
      if (parse_str("--host", args.host))
        continue;
      if (parse_int("--port", args.port))
        continue;
      if (parse_str("--grpc_host", args.grpc_host))
        continue;
      if (parse_int("--grpc_port", args.grpc_port))
        continue;
      if (parse_str("--conf", args.conf))
        continue;
      if (parse_str("--log_level", args.log_level))
        continue;
      if (parse_str("--key", args.key))
        continue;
      if (parse_str("--profile", args.profile) || parse_str("-p", args.profile))
        continue;

      // Check specific flags
      bool found_specific = false;
      for (const auto &f : specific_flags) {
        std::string flag_name = "--" + f;
        std::string val;
        if (parse_str(flag_name, val)) {
          args.extras[f] = val;
          found_specific = true;
          break;
        }
      }
      if (found_specific)
        continue;
    }

    if (args.name.empty()) {
      std::string path = argv[0];
      size_t last_slash = path.find_last_of("/\\");
      if (last_slash != std::string::npos) {
        args.name = path.substr(last_slash + 1);
      } else {
        args.name = path;
      }
    }

    return args;
  }

  static void PrintHelp(const char *prog,
                        const std::vector<std::string> &specific_flags) {
    std::cout << "Usage: " << prog << " [options]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --name <name>         Service name\n";
    std::cout << "  --host <ip>           Binding host IP\n";
    std::cout << "  --port <port>         Binding port\n";
    std::cout << "  --grpc_host <ip>      GRPC Binding host IP\n";
    std::cout << "  --grpc_port <port>     GRPC Binding port\n";
    std::cout << "  --conf <path>         Path to configuration file\n";
    std::cout << "  --log_level <level>    Logging level (DEBUG, INFO, etc.)\n";
    std::cout << "  --key <path>          Path to RSA Public/Private key\n";
    std::cout << "  --profile, -p <name>  Configuration profile\n";

    for (const auto &f : specific_flags) {
      std::cout << "  --" << f << " <value>          Specific flag: " << f
                << "\n";
    }
  }
};

} // namespace config
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_COMMAND_LINE_HPP
