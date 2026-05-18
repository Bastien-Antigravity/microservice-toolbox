#ifndef MICROSERVICE_TOOLBOX_SERIALIZERS_JSON_SERIALIZER_HPP
#define MICROSERVICE_TOOLBOX_SERIALIZERS_JSON_SERIALIZER_HPP

#include "Serializer.hpp"

namespace microservice_toolbox {
namespace serializers {

class JsonSerializer : public Serializer {
public:
    std::vector<uint8_t> Marshal(const nlohmann::json& data) override {
        std::string s = data.dump();
        return std::vector<uint8_t>(s.begin(), s.end());
    }

    nlohmann::json Unmarshal(const std::vector<uint8_t>& data) override {
        std::string s(data.begin(), data.end());
        return nlohmann::json::parse(s);
    }
};

} // namespace serializers
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_SERIALIZERS_JSON_SERIALIZER_HPP
