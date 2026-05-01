import sys
import os

# Add the toolbox to path so we can import it
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "python"))

from microservice_toolbox.serializers.providers import new_bin_serializer, new_json_serializer

def main():
    format = "msgpack"
    if len(sys.argv) > 1:
        format = sys.argv[1]

    if format == "json":
        s = new_json_serializer()
    else:
        s = new_bin_serializer()
    
    # Read binary data from stdin
    data = sys.stdin.buffer.read()
    
    try:
        decoded = s.unmarshal(data, dict)
        expected = {"name": "Integration", "value": 100}
        
        if decoded == expected:
            sys.stderr.write(f"Python: Success ({format})\n")
            sys.exit(0)
        else:
            sys.stderr.write(f"Python: Data mismatch ({format}). Got {decoded}\n")
            sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Python: Error during deserialization ({format}): {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
