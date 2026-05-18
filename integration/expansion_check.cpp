#include "../cpp/include/microservice_toolbox/config/AppConfig.hpp"
#include <iostream>

using namespace microservice_toolbox::config;

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: expansion_check <profile> <key>" << std::endl;
        return 1;
    }

    std::string profile = argv[1];
    std::string key = argv[2];

    try {
        auto ac = LoadConfig(profile);
        std::string val = ac->GetLocal(key);
        
        // Debug: print full mirror if requested key is 'DEBUG'
        if (key == "DEBUG") {
            std::cout << "MIRROR:" << ac->GetLocalJSON().dump() << std::endl;
        }

        std::cout << "VALUE:" << val;
    } catch (const std::exception& e) {
        std::cout << "VALUE:ERROR_" << e.what();
    }

    return 0;
}
