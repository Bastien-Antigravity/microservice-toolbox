// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for the Rust WireTap lock-free telemetry engine.
//
// DATA FLOW:
// Test -> Record Events -> Verify Snapshot & Sampling
//
// KEY PARAMETERS:
// - None (Unit Test Suite).
// -----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use microservice_toolbox::wiretap::*;

    #[test]
    fn test_wiretap_basic_recording_and_snapshot() {
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
        assert_eq!(snap2[0].total_frames, 1); // Frame count should not have increased
    }

    #[test]
    fn test_wiretap_power_of_two_sampling() {
        // Test mask 0 (always true)
        assert!(should_sample(0));
        assert!(should_sample(0));

        // Test mask 3 (sample every 4th item: 0b11)
        let mask = 0x3;
        let mut sampled_count = 0;
        for _ in 0..16 {
            if should_sample(mask) {
                sampled_count += 1;
            }
        }
        assert_eq!(sampled_count, 4);
    }
}

