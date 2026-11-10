#!/usr/bin/env python
# coding:utf-8

from types import SimpleNamespace as tSimpleNamespace
from unittest import TestCase as utTestCase, main as utMain

from microservice_toolbox.contracts import (
    ContractOperation,
    ContractPeer,
    ExchangeContract,
    build_contracts_envelope,
    extract_fastapi_operations,
    extract_proto_operations,
)
from microservice_toolbox.spec import build_spec_from_config


class TestContractsHelpers(utTestCase):
    def test_extract_proto_operations_and_envelope(self) -> None:
        proto = """
syntax = "proto3";
package demo_pkg;
service DemoControl {
  rpc GetStatus(StatusReq) returns (StatusResp);
  rpc Connect(stream ClientMsg) returns (stream ServerCmd);
}
"""
        ops = extract_proto_operations(proto)
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0].kind, "RPC")
        self.assertEqual(ops[0].target, "demo_pkg.DemoControl/GetStatus")
        self.assertEqual(ops[1].kind, "BIDI_STREAM")
        self.assertEqual(ops[1].input, "stream ClientMsg")
        self.assertEqual(ops[1].output, "stream ServerCmd")

        contract = ExchangeContract(
            id="grpc",
            type="gRPC / Protobuf",
            tab_label="gRPC Control",
            port=50051,
            peers=[ContractPeer(service="web_interface", role="consumer")],
            operations=ops,
            schema_format="proto3",
            schema=proto,
        )
        env = build_contracts_envelope("demo_service", "1.2.3", "unit_test", [contract])
        self.assertTrue(env["reliable"])
        self.assertTrue(env["exhaustive"])
        self.assertEqual(len(env["contracts"]), 1)
        self.assertEqual(env["contracts"][0]["tabLabel"], "gRPC Control")

    def test_extract_fastapi_operations_and_spec_forwarding(self) -> None:
        async def status_handler():
            """Returns live daemon health."""
            return {}

        mock_app = tSimpleNamespace(
            routes=[
                tSimpleNamespace(path="/api/v1/status", methods={"GET", "HEAD"}, name="get_status", endpoint=status_handler),
                tSimpleNamespace(path="/openapi.json", methods={"GET"}, name="openapi", endpoint=None),
            ]
        )
        ops = extract_fastapi_operations(mock_app)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].kind, "GET")
        self.assertEqual(ops[0].target, "/api/v1/status")
        self.assertIn("Returns live daemon health.", ops[0].description)

        mock_cfg = tSimpleNamespace(
            get_version=lambda: "1.0.0",
            get_listen_addr=lambda cap: "127.0.0.1:9000",
            get_rest_addr=lambda cap: "127.0.0.1:9001",
            get_grpc_listen_addr=lambda cap: "",
        )
        spec = build_spec_from_config(
            mock_cfg,
            "demo_cap",
            name="Demo",
            tag="demo-mfe",
            layer="L1",
            category="Base Fleet",
            description="Demo svc",
            doc_link="doc.md",
            protocol="HTTP/REST",
            framing="Port %s REST",
            contracts=[ExchangeContract(id="rest", type="HTTP/REST", operations=ops)],
        )
        d = spec.to_dict()
        self.assertEqual(len(d.get("contracts", [])), 1)
        self.assertEqual(d["contracts"][0]["id"], "rest")


if __name__ == "__main__":
    utMain()

