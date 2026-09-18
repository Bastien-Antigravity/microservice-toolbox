// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Thread-local error string storage and retrieval helpers for C++ FFI bridge.
//
// DATA FLOW:
// 1. Input: C-string error message from FFI bridge or local routines.
// 2. Logic: Allocates and copies string to thread-local or static error buffer.
// 3. Output: Exposed via set_last_error / last_error for diagnostics.
//
// KEY PARAMETERS:
// - err: The C-string error message to store.
// -----------------------------------------------------------------------------

#ifndef HELPERS_H
#define HELPERS_H

#include <stdlib.h>
#include <string.h>

extern char* last_error;

void set_last_error(const char* err);

#endif
