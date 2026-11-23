// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Embeds the canonical Cap'n Proto NotifierMsg schema as a compile-time string
// for dynamic contract reflection and OpenMFE ServiceSpec publication.
//
// DATA FLOW:
// 1. Go embed directive reads notifier.capnp at compile time.
// 2. Exposes NotifierCapnpSchema for spec.ExtractCapnpOperations and contract UI.
//
// KEY PARAMETERS:
// - NotifierCapnpSchema: Raw canonical notifier.capnp IDL definition.
// -----------------------------------------------------------------------------

package notifier

import _ "embed"

// -----------------------------------------------------------------------------

// NotifierCapnpSchema embeds the canonical Cap'n Proto binary schema for SafeSocket notification ingestion.
//
//go:embed notifier.capnp
var NotifierCapnpSchema string

