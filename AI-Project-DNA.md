# 🧬 Project DNA: microservice-toolbox

## 🎯 High-Level Intent (BDD)
- **Goal**: Unified toolkit providing common patterns (config, lifecycle, metrics) across multiple languages (Go, Python, Rust, etc.).
- **Key Pattern**: **Shared Library / SDK**.

## 🛠 Technical Constraints
- **Languages**: Multi-lang (Go, Python, Rust, C++).
- **Architecture Standard**: Adheres to the ecosystem-wide standards in [[GEMINI.md]].

## 👥 Roles & Responsibilities
- **Architect**: 
    - Ensure cross-language feature parity for core toolbox components.
    - Implement language-agnostic schemas using Protobuf or Cap'n Proto.
- **Developer**:
    - Adhere to the specific coding standards for each supported language.
    - Reference [[GEMINI.md]] for diagnostic UI helpers.
