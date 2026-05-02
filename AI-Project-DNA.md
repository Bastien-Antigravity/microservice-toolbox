# 🧬 Project DNA: microservice-toolbox

## 🎯 High-Level Intent (BDD)
- **Goal**: Provide a standardized set of cross-language utilities (Go, Python, Rust, C++, VBA) to ensure consistent behavior across the entire microservice ecosystem.
- **Key Pattern**: **Polyglot Parity** (Behavioral 1:1 match for configuration loading, retry logic, and connectivity).
- **Behavioral Source of Truth**: [[business-bdd-brain/02-Behavior-Specs/microservice-toolbox]]
- **Spec Gate**: [HARDENED] No implementation without an `approved` spec in the folder above.

## 🛠️ Role Specifics
- **Architect**: 
    - Ensure that any new utility is designed for cross-language compatibility from the start.
    - Maintain strict separation between generic infrastructure and business-specific logic.
- **QA**: 
    - Verify that a configuration change in one language's toolbox results in the exact same behavior as in another language.
    - Run the multi-language integration test suite in `integration/`.
- **Developer**:
    - Follow the specific language-native idioms (e.g., Pythonic for Python, idiomatic Rust for Rust) while preserving the shared logic.

## 🚦 Lifecycle & Versioning
- **Primary Branch**: `develop`
- **Protected Branches**: `main`, `master`
- **Versioning Strategy**: Semantic Versioning (vX.Y.Z).
- **Version Source of Truth**: `VERSION.txt`.
