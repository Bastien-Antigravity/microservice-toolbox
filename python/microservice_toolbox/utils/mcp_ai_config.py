#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Safely load, repair, and migrate MCP server configuration files
for Antigravity-IDE and gemini-cli.

DATA FLOW:
1. Read JSON config file (e.g., ~/.gemini/settings.json).
2. Detect and repair corruption (trailing commas, broken mcpServers blocks).
3. Migrate obsidian_rag entries from stdio to SSE transport.
4. Write back repaired/migrated configuration.

KEY PARAMETERS:
- filepath: Path to the JSON configuration file.
- label: Human-readable label for log messages.
- mcp_url: SSE endpoint URL for obsidian_rag migration.
"""


# -----------------------------------------------------------------------------------------------

def safe_load_and_repair_json(filepath: str, label: str, mcp_url=None) -> dict:
    """
    Safely load a JSON file. If it is corrupted (invalid syntax), attempt to repair
    it non-destructively (e.g. by fixing mcpServers blocks and trailing commas)
    to avoid wiping custom user preferences (like files.exclude).
    Also migrates any obsidian_rag stdio command configuration to SSE URL.
    """
    import os
    import re
    import json

    if not os.path.exists(filepath):
        return {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"⚠️ Error reading {label}: {e}")
        return {}

    data = None
    repaired = False

    # 1. Try strict JSON parse first
    try:
        data = json.loads(content)
    except Exception:
        pass

    if data is None:
        print(f"⚠️ Corruption detected in {label}. Attempting non-destructive repair...")
        repaired = True

        # 2. Save raw corrupted file as backup for user troubleshooting
        try:
            bak_err_path = filepath + ".err"
            with open(bak_err_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"📦 Saved raw corrupted file to {os.path.basename(bak_err_path)}")
        except Exception:
            pass

        # 3. Clean up the known source of corruption: the mcpServers key.
        cleaned = content
        try:
            pattern = re.compile(r'"mcpServers"\s*:\s*')
            match = pattern.search(cleaned)
            if match:
                start_idx = match.end()
                # Find first non-whitespace character after match.end()
                first_char_match = re.search(r'\S', cleaned[start_idx:])
                if first_char_match and first_char_match.group(0) == '{':
                    brace_start = start_idx + first_char_match.start()
                    brace_count = 0
                    in_string = False
                    escape = False
                    for i in range(brace_start, len(cleaned)):
                        char = cleaned[i]
                        if escape:
                            escape = False
                            continue
                        if char == '\\':
                            escape = True
                            continue
                        if char == '"':
                            in_string = not in_string
                            continue
                        if not in_string:
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    cleaned = cleaned[:match.start()] + '"mcpServers": {}' + cleaned[i+1:]
                                    break
                else:
                    # Fallback to replacing standard non-brace patterns
                    cleaned = re.sub(r'"mcpServers"\s*:\s*[a-zA-Z0-9_{}]+', '"mcpServers": {}', cleaned)
        except Exception:
            pass

        # 4. Clean up trailing commas
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

        # 5. Try parsing the cleaned content
        try:
            data = json.loads(cleaned)
            print(f"✅ Successfully repaired {label} non-destructively.")
        except Exception as e_repair:
            print(f"❌ Non-destructive repair failed for {label}: {e_repair}")

        # 6. Fallback: try to extract and preserve files.exclude if present
        if data is None:
            try:
                match = re.search(r'"files\.exclude"\s*:\s*(\{[^{}]*\})', content)
                if match:
                    exclude_str = match.group(1)
                    exclude_str = re.sub(r',\s*([}\]])', r'\1', exclude_str)
                    exclude_dict = json.loads(exclude_str)
                    print(f"🛡️ Recovered files.exclude from corrupted {label}.")
                    data = {
                        "files.exclude": exclude_dict,
                        "mcpServers": {}
                    }
            except Exception:
                pass

    if data is None:
        print(f"⚠️ Reverting to clean default for {label}.")
        data = {}
        repaired = True

    # 7. Migrate or initialize obsidian_rag configuration to SSE mode
    dirty = repaired
    if mcp_url:
        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            data["mcpServers"] = {}
            dirty = True
        
        mcp_servers = data["mcpServers"]
        obsidian_rag = mcp_servers.get("obsidian_rag", {})
        if not isinstance(obsidian_rag, dict):
            obsidian_rag = {}
        
        # Check if we need to update
        if (obsidian_rag.get("url") != mcp_url or 
            obsidian_rag.get("serverURL") != mcp_url or 
            "command" in obsidian_rag or 
            "args" in obsidian_rag or
            "env" in obsidian_rag):
            obsidian_rag.pop("command", None)
            obsidian_rag.pop("args", None)
            obsidian_rag.pop("env", None)
            obsidian_rag["url"] = mcp_url
            obsidian_rag["serverURL"] = mcp_url
            mcp_servers["obsidian_rag"] = obsidian_rag
            dirty = True

    # 8. Write back if repaired or migrated
    if dirty:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 Wrote updated and repaired configuration to {label}")
        except Exception as e:
            # Catch permissions/IO errors for protected files silently
            pass

    return data
