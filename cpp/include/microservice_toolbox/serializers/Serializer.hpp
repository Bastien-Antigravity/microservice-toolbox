#ifndef MICROSERVICE_TOOLBOX_SERIALIZERS_SERIALIZER_HPP
#define MICROSERVICE_TOOLBOX_SERIALIZERS_SERIALIZER_HPP

#include <vector>
#include <cstdint>
#include <string>
#include "../config/json.hpp"

namespace microservice_toolbox {
namespace serializers {

/**
 * Serializer interface manages transforming generic structs to line formats.
 */
class Serializer {
public:
    virtual ~Serializer() = default;
    
    virtual std::vector<uint8_t> Marshal(const nlohmann::json& data) = 0;
    virtual nlohmann::json Unmarshal(const std::vector<uint8_t>& data) = 0;
};

} // namespace serializers
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_SERIALIZERS_SERIALIZER_HPP
