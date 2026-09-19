// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Resolves capability network addresses and applies Docker Guard suppression rules.
//
// DATA FLOW:
// Capability Query -> Address Resolution + Docker Guard -> Final Bind Address
//
// KEY PARAMETERS:
// - requested_ip: Network IP or address to resolve.
// - Docker Guard: Suppresses localhost to 0.0.0.0 in container environments.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP
#define MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP

#include <string>
#include <cstdlib>
#include <fstream>
#include <algorithm>

namespace microservice_toolbox {
namespace connectivity {

// -----------------------------------------------------------------------------

class Resolver {
public:
    Resolver(bool force_docker = false) {
        if (force_docker) {
            is_docker = true;
        } else {
            // Check for Docker environment
            std::ifstream docker_env("/.dockerenv");
            const char* docker_env_var = std::getenv("DOCKER_ENV");
            is_docker = docker_env.good() || (docker_env_var && std::string(docker_env_var) == "true");
        }
    }

    // -----------------------------------------------------------------------------

    // Resolves the requested IP into an actual address to bind to.
    // Docker Guard Logic:
    // If running in a Docker container, this method suppresses the requested IP
    // and forces a bind to 0.0.0.0.
    std::string resolve_bind_addr(const std::string& input_ip) const {
        std::string clean_ip = input_ip;
        // Trim quotation marks
        if (clean_ip.size() >= 2 && clean_ip.front() == '"' && clean_ip.back() == '"') {
            clean_ip = clean_ip.substr(1, clean_ip.size() - 2);
        }

        // If not in Docker, use requested IP directly
        if (!is_docker) {
            return clean_ip;
        }

        // In Docker, suppress to 0.0.0.0
        return "0.0.0.0";
    }

    // -----------------------------------------------------------------------------

    // Takes a "host:port" string and returns a resolved "host:port" using Docker Guard logic.
    std::string resolve_full_bind_addr(const std::string& addr) const {
        auto colon_pos = addr.rfind(':');
        if (colon_pos == std::string::npos) {
            return resolve_bind_addr(addr);
        }

        std::string host = addr.substr(0, colon_pos);
        std::string port = addr.substr(colon_pos + 1);
        std::string resolved_host = resolve_bind_addr(host);
        return resolved_host + ":" + port;
    }

    // -----------------------------------------------------------------------------

    // Checks if the IP is a loopback address.
    bool is_loopback(const std::string& ip) const {
        return (ip.rfind("127.", 0) == 0) || (ip == "::1") || (ip == "localhost");
    }

    // -----------------------------------------------------------------------------

    bool is_docker_env() const { return is_docker; }

private:
    bool is_docker;
};

// -----------------------------------------------------------------------------

inline Resolver new_resolver() {
    return Resolver();
}

} // namespace connectivity
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP
