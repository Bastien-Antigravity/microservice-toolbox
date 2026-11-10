#ifndef MICROSERVICE_TOOLBOX_SPEC_CONTRACTS_H
#define MICROSERVICE_TOOLBOX_SPEC_CONTRACTS_H

/*
 * ESSENTIAL PROCESS:
 * Pure C11/C99 Exchange Contract data structures and RFC 8259 JSON serialization
 * helpers for microservice-toolbox. Enables C (and C/C++ FFI) services to build
 * authoritative GET /api/v1/contracts payloads and ServiceSpec contract lists
 * with zero external dependencies.
 *
 * DATA FLOW:
 * 1. Input: Microservice-owned MtExchangeContract / MtContractsEnvelope structs.
 * 2. Logic: Normalizes endpoint addresses/ports, formats UTC timestamps, and
 *    serializes escaped JSON payloads matching Go/Python/Rust wire schemas.
 * 3. Output: Heap-allocated JSON string freed via mt_spec_free_string().
 *
 * KEY PARAMETERS:
 * - MtExchangeContract: Typed protocol/channel descriptor rendered as a UI tab.
 * - MtContractsEnvelope: Top-level GET /api/v1/contracts JSON envelope.
 */

#include <ctype.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef __cplusplus
extern "C" {
#endif

// -----------------------------------------------------------------------------

typedef struct MtContractPeer {
    const char* service;
    const char* role;        // "producer" | "consumer" | "client" | "server" | "bidirectional"
    const char* description; // Optional
} MtContractPeer;

typedef struct MtContractOperation {
    const char* name;
    const char* kind;        // "GET" | "POST" | "RPC" | "BIDI_STREAM" | "PUB" | "SUB" | "TABLE" | ...
    const char* target;
    const char* input;       // Optional
    const char* output;      // Optional
    const char* description; // Optional
} MtContractOperation;

typedef struct MtExchangeContract {
    const char* id;
    const char* type;
    const char* tab_label;    // JSON key: "tabLabel"
    const char* icon;
    const char* direction;    // "inbound" | "outbound" | "bidirectional"
    const char* transport;
    const char* address;
    int port;                 // Omitted from JSON when <= 0
    const char* framing;
    const char* auth;
    const char* summary;
    const char* source;
    const MtContractPeer* peers;
    size_t peers_count;
    const MtContractOperation* operations;
    size_t operations_count;
    const char* schema_format; // JSON key: "schemaFormat"
    const char* schema;
} MtExchangeContract;

typedef struct MtContractsEnvelope {
    const char* service;
    const char* version;
    int reliable;             // Non-zero => true
    int exhaustive;           // Non-zero => true
    const char* generated_at; // JSON key: "generatedAt" (optional; auto-generated UTC if NULL/empty)
    const char* source;
    const MtExchangeContract* contracts;
    size_t contracts_count;
} MtContractsEnvelope;

// -----------------------------------------------------------------------------

typedef struct MtStrBuf {
    char* data;
    size_t len;
    size_t cap;
    int oom;
} MtStrBuf;

static inline void mt_strbuf_reserve(MtStrBuf* sb, size_t extra) {
    if (!sb || sb->oom) return;
    size_t needed = sb->len + extra + 1;
    if (needed <= sb->cap) return;
    size_t new_cap = sb->cap ? sb->cap * 2 : 256;
    while (new_cap < needed) {
        if (new_cap > ((size_t)-1) / 2) {
            new_cap = needed;
            break;
        }
        new_cap *= 2;
    }
    char* next = (char*)realloc(sb->data, new_cap);
    if (!next) {
        sb->oom = 1;
        return;
    }
    sb->data = next;
    sb->cap = new_cap;
}

static inline void mt_strbuf_append_n(MtStrBuf* sb, const char* s, size_t n) {
    if (!sb || sb->oom || !s || n == 0) return;
    mt_strbuf_reserve(sb, n);
    if (sb->oom) return;
    memcpy(sb->data + sb->len, s, n);
    sb->len += n;
    sb->data[sb->len] = '\0';
}

static inline void mt_strbuf_append(MtStrBuf* sb, const char* s) {
    if (!s) return;
    mt_strbuf_append_n(sb, s, strlen(s));
}

static inline void mt_strbuf_append_char(MtStrBuf* sb, char ch) {
    mt_strbuf_append_n(sb, &ch, 1);
}

static inline void mt_strbuf_append_json_string(MtStrBuf* sb, const char* s) {
    mt_strbuf_append_char(sb, '"');
    if (s) {
        const unsigned char* p = (const unsigned char*)s;
        while (*p && !sb->oom) {
            unsigned char c = *p++;
            switch (c) {
                case '"':  mt_strbuf_append(sb, "\\\""); break;
                case '\\': mt_strbuf_append(sb, "\\\\"); break;
                case '\b': mt_strbuf_append(sb, "\\b"); break;
                case '\f': mt_strbuf_append(sb, "\\f"); break;
                case '\n': mt_strbuf_append(sb, "\\n"); break;
                case '\r': mt_strbuf_append(sb, "\\r"); break;
                case '\t': mt_strbuf_append(sb, "\\t"); break;
                default:
                    if (c < 0x20) {
                        char esc[7];
                        snprintf(esc, sizeof(esc), "\\u%04x", (unsigned int)c);
                        mt_strbuf_append(sb, esc);
                    } else {
                        mt_strbuf_append_char(sb, (char)c);
                    }
                    break;
            }
        }
    }
    mt_strbuf_append_char(sb, '"');
}

static inline void mt_strbuf_append_opt_kv(MtStrBuf* sb, int* first, const char* key, const char* val) {
    if (!val || val[0] == '\0') return;
    if (!*first) mt_strbuf_append_char(sb, ',');
    *first = 0;
    mt_strbuf_append_json_string(sb, key);
    mt_strbuf_append_char(sb, ':');
    mt_strbuf_append_json_string(sb, val);
}

static inline void mt_strbuf_append_req_kv(MtStrBuf* sb, int* first, const char* key, const char* val) {
    if (!*first) mt_strbuf_append_char(sb, ',');
    *first = 0;
    mt_strbuf_append_json_string(sb, key);
    mt_strbuf_append_char(sb, ':');
    mt_strbuf_append_json_string(sb, val ? val : "");
}

// -----------------------------------------------------------------------------

static inline int mt_resolve_contract_port(const char* addr) {
    if (!addr || addr[0] == '\0') return 0;
    const char* colon = strrchr(addr, ':');
    if (!colon || colon[1] == '\0') return 0;
    // Skip hostnames without trailing digits (or malformed strings).
    const char* p = colon + 1;
    while (*p && isspace((unsigned char)*p)) p++;
    if (*p == '\0') return 0;
    char* endptr = NULL;
    long val = strtol(p, &endptr, 10);
    if (endptr == p || val <= 0 || val > 65535) return 0;
    while (*endptr) {
        if (!isspace((unsigned char)*endptr)) return 0;
        endptr++;
    }
    return (int)val;
}

static inline const char* mt_display_address(const char* addr, char* out_buf, size_t out_size) {
    if (!out_buf || out_size == 0) return "";
    out_buf[0] = '\0';
    if (!addr) {
        snprintf(out_buf, out_size, "%s", "dynamic");
        return out_buf;
    }
    while (*addr && isspace((unsigned char)*addr)) addr++;
    size_t len = strlen(addr);
    while (len > 0 && isspace((unsigned char)addr[len - 1])) len--;
    if (len == 0) {
        snprintf(out_buf, out_size, "%s", "dynamic");
        return out_buf;
    }
    if (addr[0] == ':') {
        snprintf(out_buf, out_size, "127.0.0.1%.*s", (int)len, addr);
        return out_buf;
    }
    if (len >= 8 && strncmp(addr, "0.0.0.0:", 8) == 0) {
        snprintf(out_buf, out_size, "127.0.0.1:%.*s", (int)(len - 8), addr + 8);
        return out_buf;
    }
    snprintf(out_buf, out_size, "%.*s", (int)len, addr);
    return out_buf;
}

static inline int mt_utc_timestamp_iso8601(char* out_buf, size_t out_size) {
    if (!out_buf || out_size < 21) return -1;
    time_t now = time(NULL);
    struct tm utc_tm;
#if defined(_WIN32)
    if (gmtime_s(&utc_tm, &now) != 0) return -1;
#else
    if (gmtime_r(&now, &utc_tm) == NULL) return -1;
#endif
    return (strftime(out_buf, out_size, "%Y-%m-%dT%H:%M:%SZ", &utc_tm) > 0) ? 0 : -1;
}

// -----------------------------------------------------------------------------

static inline void mt_write_peer_json(MtStrBuf* sb, const MtContractPeer* peer) {
    mt_strbuf_append_char(sb, '{');
    int first = 1;
    mt_strbuf_append_req_kv(sb, &first, "service", peer ? peer->service : "");
    mt_strbuf_append_req_kv(sb, &first, "role", peer ? peer->role : "");
    if (peer) mt_strbuf_append_opt_kv(sb, &first, "description", peer->description);
    mt_strbuf_append_char(sb, '}');
}

static inline void mt_write_operation_json(MtStrBuf* sb, const MtContractOperation* op) {
    mt_strbuf_append_char(sb, '{');
    int first = 1;
    mt_strbuf_append_req_kv(sb, &first, "name", op ? op->name : "");
    mt_strbuf_append_req_kv(sb, &first, "kind", op ? op->kind : "");
    mt_strbuf_append_req_kv(sb, &first, "target", op ? op->target : "");
    if (op) {
        mt_strbuf_append_opt_kv(sb, &first, "input", op->input);
        mt_strbuf_append_opt_kv(sb, &first, "output", op->output);
        mt_strbuf_append_opt_kv(sb, &first, "description", op->description);
    }
    mt_strbuf_append_char(sb, '}');
}

static inline void mt_write_contract_json(MtStrBuf* sb, const MtExchangeContract* c) {
    mt_strbuf_append_char(sb, '{');
    int first = 1;
    mt_strbuf_append_req_kv(sb, &first, "id", c ? c->id : "");
    mt_strbuf_append_req_kv(sb, &first, "type", c ? c->type : "");
    if (c) {
        mt_strbuf_append_opt_kv(sb, &first, "tabLabel", c->tab_label);
        mt_strbuf_append_opt_kv(sb, &first, "icon", c->icon);
        mt_strbuf_append_opt_kv(sb, &first, "direction", c->direction);
        mt_strbuf_append_opt_kv(sb, &first, "transport", c->transport);
        mt_strbuf_append_opt_kv(sb, &first, "address", c->address);
        if (c->port > 0) {
            char num[32];
            snprintf(num, sizeof(num), ",\"port\":%d", c->port);
            mt_strbuf_append(sb, num);
        }
        mt_strbuf_append_opt_kv(sb, &first, "framing", c->framing);
        mt_strbuf_append_opt_kv(sb, &first, "auth", c->auth);
        mt_strbuf_append_opt_kv(sb, &first, "summary", c->summary);
        mt_strbuf_append_opt_kv(sb, &first, "source", c->source);
        if (c->peers && c->peers_count > 0) {
            mt_strbuf_append(sb, ",\"peers\":[");
            for (size_t i = 0; i < c->peers_count; ++i) {
                if (i > 0) mt_strbuf_append_char(sb, ',');
                mt_write_peer_json(sb, &c->peers[i]);
            }
            mt_strbuf_append_char(sb, ']');
        }
        if (c->operations && c->operations_count > 0) {
            mt_strbuf_append(sb, ",\"operations\":[");
            for (size_t i = 0; i < c->operations_count; ++i) {
                if (i > 0) mt_strbuf_append_char(sb, ',');
                mt_write_operation_json(sb, &c->operations[i]);
            }
            mt_strbuf_append_char(sb, ']');
        }
        mt_strbuf_append_opt_kv(sb, &first, "schemaFormat", c->schema_format);
        mt_strbuf_append_opt_kv(sb, &first, "schema", c->schema);
    }
    mt_strbuf_append_char(sb, '}');
}

static inline char* mt_contract_peer_to_json(const MtContractPeer* peer) {
    MtStrBuf sb = {NULL, 0, 0, 0};
    mt_write_peer_json(&sb, peer);
    if (sb.oom) { free(sb.data); return NULL; }
    return sb.data;
}

static inline char* mt_contract_operation_to_json(const MtContractOperation* op) {
    MtStrBuf sb = {NULL, 0, 0, 0};
    mt_write_operation_json(&sb, op);
    if (sb.oom) { free(sb.data); return NULL; }
    return sb.data;
}

static inline char* mt_exchange_contract_to_json(const MtExchangeContract* contract) {
    MtStrBuf sb = {NULL, 0, 0, 0};
    mt_write_contract_json(&sb, contract);
    if (sb.oom) { free(sb.data); return NULL; }
    return sb.data;
}

static inline char* mt_contracts_envelope_to_json(const MtContractsEnvelope* env) {
    MtStrBuf sb = {NULL, 0, 0, 0};
    char ts_buf[32];
    const char* service = (env && env->service) ? env->service : "";
    const char* version = (env && env->version && env->version[0] != '\0') ? env->version : "0.0.1";
    const char* gen_at = (env && env->generated_at && env->generated_at[0] != '\0') ? env->generated_at : NULL;
    if (!gen_at) {
        if (mt_utc_timestamp_iso8601(ts_buf, sizeof(ts_buf)) == 0) {
            gen_at = ts_buf;
        } else {
            gen_at = "1970-01-01T00:00:00Z";
        }
    }
    char default_src[256];
    const char* source = (env && env->source && env->source[0] != '\0') ? env->source : NULL;
    if (!source) {
        snprintf(default_src, sizeof(default_src), "%s runtime", service[0] ? service : "microservice");
        source = default_src;
    }

    mt_strbuf_append_char(&sb, '{');
    int first = 1;
    mt_strbuf_append_req_kv(&sb, &first, "service", service);
    mt_strbuf_append_opt_kv(&sb, &first, "version", version);
    mt_strbuf_append(&sb, (env && env->reliable) ? ",\"reliable\":true" : ",\"reliable\":false");
    mt_strbuf_append(&sb, (env && env->exhaustive) ? ",\"exhaustive\":true" : ",\"exhaustive\":false");
    mt_strbuf_append_req_kv(&sb, &first, "generatedAt", gen_at);
    mt_strbuf_append_req_kv(&sb, &first, "source", source);
    mt_strbuf_append(&sb, ",\"contracts\":[");
    if (env && env->contracts && env->contracts_count > 0) {
        for (size_t i = 0; i < env->contracts_count; ++i) {
            if (i > 0) mt_strbuf_append_char(&sb, ',');
            mt_write_contract_json(&sb, &env->contracts[i]);
        }
    }
    mt_strbuf_append(&sb, "]}");
    if (sb.oom) {
        free(sb.data);
        return NULL;
    }
    return sb.data;
}

static inline void mt_spec_free_string(char* ptr) {
    free(ptr);
}

#ifdef __cplusplus
}
#endif

#endif // MICROSERVICE_TOOLBOX_SPEC_CONTRACTS_H

