// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Embeds the canonical Cap'n Proto LoggerMsg schema as a compile-time string
// for dynamic contract reflection and OpenMFE ServiceSpec publication.
//
// DATA FLOW:
// 1. Go embed directive reads logger.capnp at compile time.
// 2. Exposes LoggerCapnpSchema for spec.ExtractCapnpOperations and contract UI.
//
// KEY PARAMETERS:
// - LoggerCapnpSchema: Raw canonical logger.capnp IDL definition.
// -----------------------------------------------------------------------------

package logger

import _ "embed"

// -----------------------------------------------------------------------------

// LoggerCapnpSchema embeds the canonical Cap'n Proto binary schema for SafeSocket log ingestion.
//
//go:embed logger.capnp
var LoggerCapnpSchema string

