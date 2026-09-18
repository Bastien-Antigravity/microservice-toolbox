---
microservice: microservice-toolbox
type: note
status: active
tags:
- '#service/microservice-toolbox'
- '#type/note'
- '#state/active'
- '#zone/3-fleet'
---

# 🧬 Project DNA: microservice-toolbox

## Metadata
- Version: 0.0.1
- Classification: Library

## 🎯 High-Level Intent (BDD)
- **Goal**: Unified toolkit providing common patterns (config, lifecycle, metrics) across multiple languages (Go, Python, Rust, etc.).
- **Key Pattern**: **Shared Library / SDK**.

## 🛠 Technical Constraints
- **Languages**: Multi-lang (Go, Python, Rust, C++).
- **Architecture Standard**: Adheres to the ecosystem-wide standards in `obsidian-brain/03-Tech-Stack`.

## 👥 Roles & Responsibilities
- **Architect**: 
    - Ensure cross-language feature parity for core toolbox components.
    - Implement language-agnostic schemas using Protobuf or Cap'n Proto.
- **Developer**:
    - Adhere to the specific coding standards for each supported language.
    - Reference `obsidian-brain` for ecosystem contracts and diagnostic UI helpers.
