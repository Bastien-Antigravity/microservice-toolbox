# Testing: VBA Microservice Toolbox

Testing in VBA is performed via the Immediate Window and specialized test procedures within the project.

## Verification Steps
1.  **Library Path**: Verify that `libdistconf.dll` is accessible.
2.  **Immediate Window**:
    ```vba
    Set ac = New AppConfig
    ac.Init "standalone"
    ? ac.GetProfile  ' Should return "standalone"
    ```

## Key Test Areas
- **String Conversion**: Verifying that non-ASCII characters survive the BSTR -> C-string -> BSTR roundtrip.
- **YAML Parsing**: Ensuring the `LoadLocalOverrides` correctly identifies the `private:` block in `.yaml` files.
- **FFI Stability**: Confirming that `Class_Terminate` correctly calls `DistConf_Close` to prevent memory leaks in the Excel process.
