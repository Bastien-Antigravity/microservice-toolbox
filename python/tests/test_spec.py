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

from os import environ as osEnviron
from os.path import join as osPathJoin
from tempfile import TemporaryDirectory as tmpTemporaryDirectory
from unittest import TestCase as utTestCase, main as utMain
from unittest.mock import MagicMock as mockMagicMock, patch as mockPatch

from microservice_toolbox.config import load_config
from microservice_toolbox.spec import (
    ServiceSpec,
    build_spec_from_config,
    publish_service_spec,
    resolve_mfe_url,
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

    # -------------------------------------------------------------------------------------------
    def test_brain_id_resolution_and_serialization(self) -> None:
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

        clean_env = {k: v for k, v in osEnviron.items() if k not in ("BRAIN_ID", "TARGET_BRAIN_ID")}
        with mockPatch.dict("os.environ", clean_env, clear=True):
            spec_empty = build_spec_from_config(mock_cfg, "config_server", **valid_kwargs)
            self.assertIsNone(spec_empty.brain_id)
            self.assertNotIn("brain_id", spec_empty.to_dict())

        with mockPatch.dict("os.environ", {**clean_env, "TARGET_BRAIN_ID": "brain-target"}, clear=True):
            spec_target = build_spec_from_config(mock_cfg, "config_server", **valid_kwargs)
            self.assertEqual(spec_target.brain_id, "brain-target")
            self.assertEqual(spec_target.to_dict().get("brain_id"), "brain-target")

        with mockPatch.dict("os.environ", {**clean_env, "BRAIN_ID": "brain-primary", "TARGET_BRAIN_ID": "brain-target"}, clear=True):
            spec_primary = build_spec_from_config(mock_cfg, "config_server", **valid_kwargs)
            self.assertEqual(spec_primary.brain_id, "brain-primary")
            self.assertEqual(spec_primary.to_dict().get("brain_id"), "brain-primary")

            spec_explicit = build_spec_from_config(mock_cfg, "config_server", brain_id="brain-explicit", **valid_kwargs)
            self.assertEqual(spec_explicit.brain_id, "brain-explicit")
            self.assertEqual(spec_explicit.to_dict().get("brain_id"), "brain-explicit")

        with mockPatch("microservice_toolbox.spec.publish") as mock_publish:
            publish_service_spec(mock_cfg, None, "config_server", brain_id="brain-param", **valid_kwargs)
            mock_publish.assert_called_once()
            _, _, called_kwargs = mock_publish.mock_calls[0]
            self.assertEqual(called_kwargs.get("brain_id"), "brain-param")

        # Capability resolution priority: squad_agent.target_brain_id > watchdog_agent.brain_id > BRAIN_ID > TARGET_BRAIN_ID
        cap_store = {
            "watchdog_agent": {"brain_id": "watchdog-brain"},
        }
        mock_cfg.get_capability.side_effect = lambda cap: cap_store.get(cap, {})
        with mockPatch.dict("os.environ", {**clean_env, "BRAIN_ID": "brain-primary", "TARGET_BRAIN_ID": "brain-target"}, clear=True):
            spec_wd = build_spec_from_config(mock_cfg, "config_server", **valid_kwargs)
            self.assertEqual(spec_wd.brain_id, "watchdog-brain")

            cap_store["squad_agent"] = {"target_brain_id": "squad-brain"}
            spec_sq = build_spec_from_config(mock_cfg, "config_server", **valid_kwargs)
            self.assertEqual(spec_sq.brain_id, "squad-brain")

            spec_ov = build_spec_from_config(mock_cfg, "config_server", brain_id="brain-explicit", **valid_kwargs)
            self.assertEqual(spec_ov.brain_id, "brain-explicit")

    # -------------------------------------------------------------------------------------------
    def test_standalone_yaml_brain_id_zero_env(self) -> None:
        with tmpTemporaryDirectory() as tmp_dir:
            yaml_path = osPathJoin(tmp_dir, "standalone.yaml")
            with open(yaml_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "common:\n"
                    "  name: order_router\n"
                    "capabilities:\n"
                    "  order_router:\n"
                    "    ip: 127.0.0.1\n"
                    "    port: 14100\n"
                    "  squad_agent:\n"
                    "    target_brain_id: \"trading-brain\"\n"
                )

            clean_env = {
                k: v for k, v in osEnviron.items()
                if k not in ("BRAIN_ID", "TARGET_BRAIN_ID", "CONFIG_PATH", "SHARED_CONFIG_PATH")
            }
            clean_env["CONFIG_PATH"] = yaml_path
            with mockPatch.dict("os.environ", clean_env, clear=True):
                cfg = load_config("standalone", specific_flags=[], input_args=[])
                spec = build_spec_from_config(
                    cfg,
                    "order_router",
                    name="Order Router",
                    tag="order-router-mfe",
                    layer="L3",
                    category="Domain Services",
                    description="Routes trading orders.",
                    doc_link="obsidian-brain/06-Microservices/Order-Router.md",
                    protocol="TCP",
                    framing="Port %s TCP",
                )
                self.assertEqual(spec.brain_id, "trading-brain")
                self.assertEqual(spec.to_dict().get("brain_id"), "trading-brain")

    # -------------------------------------------------------------------------------------------
    def test_docker_mfe_url_resolution(self) -> None:
        mock_cfg = mockMagicMock()
        mock_cfg.get_version.return_value = "0.0.1"
        mock_cfg.get_public_ip.return_value = "127.0.0.2"
        mock_cfg.get_listen_addr.side_effect = lambda cap: "0.0.0.0:8085" if cap == "squad_agent" else None
        mock_cfg.get_rest_addr.side_effect = lambda cap: "0.0.0.0:8085" if cap == "squad_agent" else None
        mock_cfg.get_grpc_listen_addr.side_effect = lambda cap: None

        valid_kwargs = {
            "name": "Squad Agent",
            "tag": "squad-agent-mfe",
            "layer": "L3",
            "category": "Domain Services",
            "description": "Autonomous squad runtime.",
            "doc_link": "obsidian-brain/06-Microservices/Squad-Agent-Hub.md",
            "protocol": "REST",
            "framing": "Port %s REST",
        }

        clean_env = {k: v for k, v in osEnviron.items() if k not in ("DOCKER_ENV", "HOST_IP")}
        with mockPatch.dict("os.environ", {**clean_env, "DOCKER_ENV": "true"}, clear=True):
            spec = build_spec_from_config(mock_cfg, "squad_agent", **valid_kwargs)
            self.assertEqual(spec.url, "http://127.0.0.2:8085")
            self.assertEqual(
                resolve_mfe_url(mock_cfg, "http://log-shipper:9095/static/mfe.js"),
                "http://127.0.0.2:9095/static/mfe.js",
            )

        with mockPatch.dict("os.environ", {**clean_env, "DOCKER_ENV": "true", "HOST_IP": "203.0.113.10"}, clear=True):
            self.assertEqual(
                resolve_mfe_url(mock_cfg, "http://0.0.0.0:8085/static/mfe.js"),
                "http://203.0.113.10:8085/static/mfe.js",
            )


# -----------------------------------------------------------------------------------------------
if __name__ == "__main__":
    utMain()
