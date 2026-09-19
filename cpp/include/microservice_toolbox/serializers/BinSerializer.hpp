// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Binary MsgPack serializer implementing the unified Serializer interface.
//
// DATA FLOW:
// json Objects <-> BinSerializer (MsgPack) <-> Byte Payloads
//
// KEY PARAMETERS:
// - Marshal: Serializes json object into binary MsgPack format.
// - Unmarshal: Deserializes MsgPack byte payload back into json.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_SERIALIZERS_BIN_SERIALIZER_HPP
#define MICROSERVICE_TOOLBOX_SERIALIZERS_BIN_SERIALIZER_HPP

#include "Serializer.hpp"

namespace microservice_toolbox {
namespace serializers {

// -----------------------------------------------------------------------------

class BinSerializer : public Serializer {
public:
    std::vector<uint8_t> Marshal(const nlohmann::json& data) override {
        return nlohmann::json::to_msgpack(data);
    }

    nlohmann::json Unmarshal(const std::vector<uint8_t>& data) override {
        return nlohmann::json::from_msgpack(data);
    }
};

// -----------------------------------------------------------------------------

} // namespace serializers
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_SERIALIZERS_BIN_SERIALIZER_HPP
