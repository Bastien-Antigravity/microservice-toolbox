import pytest

from microservice_toolbox.serializers.providers import new_bin_serializer, new_json_serializer


class DataForTest:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __eq__(self, other):
        return self.__dict__ == other.__dict__


def test_serializers_roundtrip():
    # Note: MsgPack unmarshals into dicts by default in the BinSerializer implementation
    data = {"name": "Toolbox", "value": 42}

    json_s = new_json_serializer()
    bin_s = new_bin_serializer()

    for s in [json_s, bin_s]:
        # Marshal
        encoded = s.marshal(data)
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

        # Unmarshal
        decoded = s.unmarshal(encoded, dict)
        assert decoded == data


def test_json_serializer_error():
    json_s = new_json_serializer()
    with pytest.raises(ValueError, match="json unmarshal error"):
        json_s.unmarshal(b"invalid json", dict)


def test_bin_serializer_error():
    bin_s = new_bin_serializer()
    with pytest.raises(ValueError, match="msgpack unmarshal error"):
        bin_s.unmarshal(b"\xc1", dict)
