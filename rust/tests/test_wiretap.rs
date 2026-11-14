// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for the Rust WireTap lock-free telemetry engine.
//
// DATA FLOW:
// Test -> Record Events -> Verify Snapshot & Sampling
//
// KEY PARAMETERS:
// - TEST_MUTEX: Serializes tests mutating global WireTap singleton state.
// -----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use microservice_toolbox::wiretap::*;
    use std::sync::Mutex;

    static TEST_MUTEX: Mutex<()> = Mutex::new(());

    #[test]
    fn test_wiretap_basic_recording_and_snapshot() {
        let _guard = TEST_MUTEX.lock().unwrap_or_else(|e| e.into_inner());
        reset();
        set_enabled(true);
        assert!(is_enabled());

        record_event(
            "log-server",
            "web-interface",
            "SAFESOCKET",
            "frame",
            "log:stream",
            "frame",
            "outbound",
            Some("test payload"),
            1024,
            1.5,
            false,
            false,
        );

        let snap = snapshot();
        assert_eq!(snap.len(), 1);
        let edge = &snap[0];
        assert_eq!(edge.source, "log_server");
        assert_eq!(edge.target, "web_interface");
        assert_eq!(edge.protocol, "SAFESOCKET");
        assert_eq!(edge.total_frames, 1);
        assert_eq!(edge.total_bytes, 1024);
        assert_eq!(edge.channels.len(), 1);
        assert_eq!(edge.channels[0].channel, "log:stream");
        assert_eq!(edge.channels[0].frames, 1);
        assert_eq!(edge.channels[0].bytes, 1024);
        assert_eq!(edge.channels[0].last_payload, Some("test payload".to_string()));

        // Test toggle OFF
        set_enabled(false);
        assert!(!is_enabled());
        record_event(
            "log-server",
            "web-interface",
            "SAFESOCKET",
            "frame",
            "log:stream",
            "frame",
            "outbound",
            None,
            512,
            0.0,
            false,
            false,
        );
        let snap2 = snapshot();
        assert_eq!(snap2[0].total_frames, 1);
        set_enabled(true);
        reset();
    }

    #[test]
    fn test_wiretap_power_of_two_sampling() {
        assert!(should_sample(0));
        assert!(should_sample(0));

        let mask = 0x3;
        let mut sampled_count = 0;
        for _ in 0..16 {
            if should_sample(mask) {
                sampled_count += 1;
            }
        }
        assert_eq!(sampled_count, 4);
    }

    #[test]
    fn test_wiretap_merge_and_framing_parity() {
        let _guard = TEST_MUTEX.lock().unwrap_or_else(|e| e.into_inner());
        reset();
        assert!(is_enabled());
        set_local_service("test-svc");
        assert_eq!(get_local_service(), "test_svc");
        set_web_hub_url("http://127.0.0.1:5000/");
        assert_eq!(get_web_hub_url(), "http://127.0.0.1:5000");

        record_event("a", "b", "TCP", "raw", "ch1", "data", "outbound", None, 10, 0.5, false, false);
        record_event("a", "b", "TCP", "SafeSocket/TCP", "ch1", "data", "outbound", None, 20, 0.5, false, false);
        let snap = snapshot();
        assert_eq!(snap.len(), 1);
        assert_eq!(snap[0].framing, "SafeSocket/TCP");
        assert!(snap[0].last_seen.ends_with('Z'));
        assert!(!snap[0].last_seen.contains('.'));

        merge_remote_snapshot(&[EdgeReport {
            source: "svc-x".to_string(),
            target: "nats_server".to_string(),
            protocol: "NATS".to_string(),
            framing: "NATS JetStream".to_string(),
            active_conns: 1,
            total_frames: 5,
            total_bytes: 500,
            total_errors: 0,
            last_seen: "2026-11-10T00:00:00Z".to_string(),
            is_external: false,
            channels: vec![],
        }]);
        let merged = snapshot();
        assert_eq!(merged.len(), 2);
        assert_eq!(merged[1].source, "svc_x");
        assert_eq!(merged[1].target, "nats");
        reset();
    }
}
