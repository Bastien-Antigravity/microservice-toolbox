#ifndef MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP
#define MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP

#include <string>
#include <cstdlib>
#include <fstream>

namespace microservice_toolbox {
namespace connectivity {

class Resolver {
public:
    Resolver() {
        // Check for Docker environment
        std::ifstream docker_env("/.dockerenv");
        const char* docker_env_var = std::getenv("DOCKER_ENV");
        
        is_docker = docker_env.good() || (docker_env_var && std::string(docker_env_var) == "true");
    }

    std::string resolve_bind_addr(const std::string& input_ip) const {
        // If not in Docker, always return the input IP (usually 0.0.0.0 or 127.0.0.1)
        if (!is_docker) {
            return input_ip;
        }

        // If in Docker and input is a specific external IP, keep it
        if (input_ip != "0.0.0.0" && input_ip != "127.0.0.1") {
            return input_ip;
        }

        // In Docker, we typically want to bind to all interfaces or use a specific strategy.
        // For now, mirroring the Go/Python/Rust behavior of returning the input 
        // unless specific Docker-to-Host translation is needed.
        return input_ip;
    }

    bool is_docker_env() const { return is_docker; }

private:
    bool is_docker;
};

} // namespace connectivity
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_CONNECTIVITY_RESOLVER_HPP
