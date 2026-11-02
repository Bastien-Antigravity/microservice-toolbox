#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for Python ServiceSpec dynamic validation, port extraction,
zero-fallback fail-fast verification, and web_interface registration.

DATA FLOW:
1. Valid ServiceSpec + Mock AppConfig -> build_spec_from_config -> Validate extracted ports & metadata
2. Missing metadata fields -> build_spec_from_config -> Verify fail-fast ValueError
3. Missing web_interface -> publish_service_spec -> Verify fail-fast RuntimeError

KEY PARAMETERS:
- None (Unit Test Suite).
"""

from unittest import TestCase as utTestCase, main as utMain
from unittest.mock import MagicMock as mockMagicMock

from microservice_toolbox.spec import (
    ServiceSpec,
    build_spec_from_config,
    publish_service_spec,
)


# -----------------------------------------------------------------------------------------------
class TestPythonSpec(utTestCase):
    def test_build_spec_from_config_valid(self) -> None:
        mock_cfg = mockMagicMock()
        mock_cfg.get_version.return_value = "2.3.4"
        mock_cfg.get_listen_addr.side_effect = lambda cap: "127.0.0.1:3306" if cap == "config_server" else None
        mock_cfg.get_rest_addr.side_effect = lambda cap: "127.0.0.1:3308" if cap == "config_server" else None
        mock_cfg.get_grpc_listen_addr.side_effect = lambda cap: "127.0.0.1:3307" if cap == "config_server" else None

        spec = build_spec_from_config(
            mock_cfg,
            "config_server",
            name="Config Server",
            tag="config-server-mfe",
            layer="L1",
            category="Base Fleet",
            description="Centralized configuration repository.",
            doc_link="obsidian-brain/06-Microservices/Config-Server-Hub.md",
            protocol="TCP, REST & gRPC",
            framing="Port %s TCP / Port %s REST",
        )
        self.assertEqual(spec.name, "Config Server")
        self.assertEqual(spec.capability, "config_server")
        self.assertEqual(spec.layer, "L1")
        self.assertEqual(spec.category, "Base Fleet")
        self.assertIn("3306", spec.framing)
        self.assertIn("3308", spec.framing)
        self.assertEqual(spec.doc_link, "obsidian-brain/06-Microservices/Config-Server-Hub.md")
        self.assertEqual(spec.data_structure.get("version"), "2.3.4")
        self.assertEqual(spec.url, "http://127.0.0.1:3308")

    # -------------------------------------------------------------------------------------------
    def test_build_spec_from_config_fail_fast(self) -> None:
        mock_cfg = mockMagicMock()
        mock_cfg.get_version.return_value = "2.3.4"
        mock_cfg.get_listen_addr.side_effect = lambda cap: "127.0.0.1:3306" if cap == "config_server" else None
        mock_cfg.get_rest_addr.side_effect = lambda cap: None
        mock_cfg.get_grpc_listen_addr.side_effect = lambda cap: None

        valid_kwargs = {
            "name": "Config Server",
            "tag": "config-server-mfe",
            "layer": "L1",
            "category": "Base Fleet",
            "description": "Centralized configuration repository.",
            "doc_link": "obsidian-brain/06-Microservices/Config-Server-Hub.md",
            "protocol": "TCP",
            "framing": "Port %s TCP",
        }

        # 1. app_config is None
        with self.assertRaises(ValueError):
            build_spec_from_config(None, "config_server", **valid_kwargs)

        # 2. empty capability
        with self.assertRaises(ValueError):
            build_spec_from_config(mock_cfg, "", **valid_kwargs)

        # 3. missing name
        kw = dict(valid_kwargs, name="")
        with self.assertRaises(ValueError):
            build_spec_from_config(mock_cfg, "config_server", **kw)

        # 4. missing layer
        kw = dict(valid_kwargs, layer="")
        with self.assertRaises(ValueError):
            build_spec_from_config(mock_cfg, "config_server", **kw)

        # 5. missing category
        kw = dict(valid_kwargs, category="")
        with self.assertRaises(ValueError):
            build_spec_from_config(mock_cfg, "config_server", **kw)

        # 6. missing description
        kw = dict(valid_kwargs, description="")
        with self.assertRaises(ValueError):
            build_spec_from_config(mock_cfg, "config_server", **kw)

        # 7. missing doc_link
        kw = dict(valid_kwargs, doc_link="")
        with self.assertRaises(ValueError):
            build_spec_from_config(mock_cfg, "config_server", **kw)

        # 8. missing protocol
        kw = dict(valid_kwargs, protocol="")
        with self.assertRaises(ValueError):
            build_spec_from_config(mock_cfg, "config_server", **kw)

        # 9. missing framing
        kw = dict(valid_kwargs, framing="")
        with self.assertRaises(ValueError):
            build_spec_from_config(mock_cfg, "config_server", **kw)

        # 10. Capability with no addresses
        with self.assertRaises(RuntimeError):
            build_spec_from_config(mock_cfg, "unknown_capability", **valid_kwargs)

    # -------------------------------------------------------------------------------------------
    def test_publish_service_spec_fail_fast(self) -> None:
        valid_kwargs = {
            "name": "Config Server",
            "tag": "config-server-mfe",
            "layer": "L1",
            "category": "Base Fleet",
            "description": "Centralized configuration repository.",
            "doc_link": "obsidian-brain/06-Microservices/Config-Server-Hub.md",
            "protocol": "TCP",
            "framing": "Port %s TCP",
        }

        # 1. app_config is None
        with self.assertRaises(ValueError):
            publish_service_spec(None, None, "config_server", **valid_kwargs)

        # 2. web_interface missing
        mock_cfg = mockMagicMock()
        mock_cfg.get_listen_addr.side_effect = lambda cap: None if cap == "web_interface" else "127.0.0.1:3306"
        with self.assertRaises(RuntimeError):
            publish_service_spec(mock_cfg, None, "config_server", **valid_kwargs)

    # -------------------------------------------------------------------------------------------
    def test_publish_parity_and_exports(self) -> None:
        import microservice_toolbox as mt

        # Verify 100% parity exports in top-level __init__
        self.assertTrue(callable(mt.publish))
        self.assertTrue(callable(mt.publish_sync))
        self.assertTrue(callable(mt.publish_with_lifecycle))
        self.assertTrue(callable(mt.build_spec_from_config))
        self.assertTrue(callable(mt.Publish))
        self.assertTrue(callable(mt.PublishWithLifecycle))
        self.assertTrue(callable(mt.PublishSync))
        self.assertTrue(callable(mt.BuildSpecFromConfig))
        self.assertIs(mt.ServiceSpec, ServiceSpec)

        valid_kwargs = {
            "name": "Config Server",
            "tag": "config-server-mfe",
            "layer": "L1",
            "category": "Base Fleet",
            "description": "Centralized configuration repository.",
            "doc_link": "obsidian-brain/06-Microservices/Config-Server-Hub.md",
            "protocol": "TCP",
            "framing": "Port %s TCP",
        }

        # publish() fail-fast when app_config is None
        with self.assertRaises(ValueError):
            mt.publish(None, None, "config_server", **valid_kwargs)

        # publish_sync() fail-fast when web_interface is missing
        mock_cfg = mockMagicMock()
        mock_cfg.get_listen_addr.side_effect = lambda cap: None if cap == "web_interface" else "127.0.0.1:3306"
        with self.assertRaises(RuntimeError):
            mt.publish_sync(mock_cfg, None, "config_server", **valid_kwargs)


# -----------------------------------------------------------------------------------------------
if __name__ == "__main__":
    utMain()
