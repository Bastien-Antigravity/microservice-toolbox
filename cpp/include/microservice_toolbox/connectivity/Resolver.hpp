// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Resolves configured capability network addresses strictly from AppConfig inputs.
//
// DATA FLOW:
// Config Address Input -> Validation + Host/Port Split -> Final Bind Address
//
// KEY PARAMETERS:
// - requested_ip: Configured bind IP/host (zero hardcoded defaults).
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP
#define MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <stdexcept>
#include <string>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace microservice_toolbox {
namespace connectivity {

// -----------------------------------------------------------------------------

class Resolver {
public:
    bool is_docker{false};

    Resolver() {
        std::ifstream docker_env("/.dockerenv");
        const char* docker_env_var = std::getenv("DOCKER_ENV");
        is_docker = docker_env.good() || (docker_env_var && std::string(docker_env_var) == "true");
    }

    explicit Resolver(bool force_docker) : is_docker(force_docker) {}

    // -----------------------------------------------------------------------------

    std::string resolve_bind_addr(const std::string& input_ip) const {
        auto notSpace = [](unsigned char c) { return !std::isspace(c); };
        if (std::find_if(input_ip.begin(), input_ip.end(), notSpace) == input_ip.end()) {
            throw std::invalid_argument("Resolver::resolve_bind_addr: configured bind IP must not be empty (FAIL-FAST)");
        }
        return input_ip;
    }

    std::string ResolveBindAddr(const std::string& input_ip) const {
        return resolve_bind_addr(input_ip);
    }

    // -----------------------------------------------------------------------------

    std::string resolve_full_bind_addr(const std::string& addr) const {
        auto notSpace = [](unsigned char c) { return !std::isspace(c); };
        if (std::find_if(addr.begin(), addr.end(), notSpace) == addr.end()) {
            throw std::invalid_argument("Resolver::resolve_full_bind_addr: configured bind address must not be empty (FAIL-FAST)");
        }

        if (addr.front() == '[') {
            size_t bracket_colon = addr.rfind("]:");
            if (bracket_colon != std::string::npos) {
                std::string host = addr.substr(1, bracket_colon - 1);
                std::string port = addr.substr(bracket_colon + 2);
                if (std::find_if(port.begin(), port.end(), notSpace) == port.end()) {
                    throw std::invalid_argument("Resolver::resolve_full_bind_addr: configured port must not be empty (FAIL-FAST)");
                }
                std::string resolved_host = resolve_bind_addr(host);
                return (resolved_host.find(':') != std::string::npos)
                           ? "[" + resolved_host + "]:" + port
                           : resolved_host + ":" + port;
            }
            return resolve_bind_addr(addr);
        }

        if (std::count(addr.begin(), addr.end(), ':') == 1) {
            size_t colon_pos = addr.find(':');
            std::string host = addr.substr(0, colon_pos);
            std::string port = addr.substr(colon_pos + 1);
            if (std::find_if(port.begin(), port.end(), notSpace) == port.end()) {
                throw std::invalid_argument("Resolver::resolve_full_bind_addr: configured port must not be empty (FAIL-FAST)");
            }
            return resolve_bind_addr(host) + ":" + port;
        }

        return resolve_bind_addr(addr);
    }

    std::string ResolveFullBindAddr(const std::string& addr) const {
        return resolve_full_bind_addr(addr);
    }

    // -----------------------------------------------------------------------------

    bool is_loopback(const std::string& ip) const {
        if (ip.rfind("127.", 0) == 0 || ip == "::1") {
            return true;
        }
        std::string lower = ip;
        std::transform(lower.begin(), lower.end(), lower.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        return lower == "localhost";
    }

    bool IsLoopback(const std::string& ip) const {
        return is_loopback(ip);
    }

    // -----------------------------------------------------------------------------

    std::string get_primary_interface_ip() const {
        std::string resolved;
#if !defined(_WIN32)
        struct ifaddrs* ifaddr = nullptr;
        if (::getifaddrs(&ifaddr) == 0 && ifaddr != nullptr) {
            for (struct ifaddrs* ifa = ifaddr; ifa != nullptr; ifa = ifa->ifa_next) {
                if (!ifa->ifa_addr || ifa->ifa_addr->sa_family != AF_INET) {
                    continue;
                }
                if ((ifa->ifa_flags & IFF_UP) == 0 || (ifa->ifa_flags & IFF_LOOPBACK) != 0) {
                    continue;
                }
                char buf[INET_ADDRSTRLEN] = {0};
                const auto* sin = reinterpret_cast<const sockaddr_in*>(ifa->ifa_addr);
                if (inet_ntop(AF_INET, &sin->sin_addr, buf, sizeof(buf)) != nullptr) {
                    std::string candidate(buf);
                    if (!candidate.empty() && !is_loopback(candidate)) {
                        resolved = candidate;
                        break;
                    }
                }
            }
            ::freeifaddrs(ifaddr);
        }
#endif
        if (resolved.empty()) {
            throw std::runtime_error("Resolver: no primary network interface found");
        }
        return resolved;
    }

    std::string GetPrimaryInterfaceIP() const {
        return get_primary_interface_ip();
    }

    // -----------------------------------------------------------------------------

    bool is_docker_env() const { return is_docker; }
    bool IsDockerEnv() const { return is_docker; }
};

// -----------------------------------------------------------------------------

inline Resolver new_resolver() {
    return Resolver();
}

inline Resolver NewResolver() {
    return Resolver();
}

} // namespace connectivity
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP
