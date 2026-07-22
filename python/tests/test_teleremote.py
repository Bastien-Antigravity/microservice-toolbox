#!/usr/bin/env python
# coding:utf-8

import asyncio
import json
from unittest.mock import Mock

import grpc
from microservice_toolbox.teleremote.client import Action, TeleClient
from microservice_toolbox.teleremote.grpc_client import teleremote_pb2, teleremote_pb2_grpc


def test_action_and_menu_generation():
    """Verify recursive menu serialization and omitempty parity."""
    client = TeleClient("TestApp", "127.0.0.1", 50051)

    # 1. Leaf command
    h1 = Mock()
    a1 = Action(label="Command 1", callback=h1)

    # 2. Submenu
    h2 = Mock()
    sub_a = Action(label="Sub Command", callback=h2, input_prompt="Enter text:")
    a2 = Action(label="Menu 1", sub_menu=[sub_a])

    client.add_action(a1)
    client.add_action(a2)

    # Check handler registration
    assert "Command 1" in client._handlers
    assert "Sub Command" in client._handlers
    assert "Menu 1" not in client._handlers  # Menu has no callback

    menu_json = client.generate_menu_json()
    menu = json.loads(menu_json)

    # Output structure check
    assert len(menu) == 2
    # Check leaf
    btn1 = menu[0]["buttons"][0]
    assert btn1["label"] == "Command 1"
    assert btn1["cmd_type"] == 99
    assert btn1["payload"] == "Command 1"
    assert "input_prompt" not in btn1
    assert "menu" not in btn1

    # Check submenu
    btn2 = menu[1]["buttons"][0]
    assert btn2["label"] == "Menu 1"
    assert "cmd_type" not in btn2
    assert "payload" not in btn2
    assert "input_prompt" not in btn2
    assert "menu" in btn2

    sub_btn = btn2["menu"][0]["buttons"][0]
    assert sub_btn["label"] == "Sub Command"
    assert sub_btn["input_prompt"] == "Enter text:"
    assert sub_btn["cmd_type"] == 99
    assert sub_btn["payload"] == "Sub Command"


def test_teleclient_integration():
    """End-to-end integration test with a mock gRPC server using asyncio.run."""
    
    class MockTeleRemoteService(teleremote_pb2_grpc.TeleRemoteServiceServicer):
        def __init__(self):
            self.registrations = []
            self.telemetries = []
            self.commands_to_send = asyncio.Queue()
            self.done = asyncio.Event()

        async def Connect(self, request_iterator, context):
            async def read_requests():
                try:
                    async for msg in request_iterator:
                        if msg.HasField("registration"):
                            self.registrations.append(msg)
                        elif msg.HasField("telemetry"):
                            self.telemetries.append(msg.telemetry)
                except Exception:
                    pass
                finally:
                    self.done.set()

            task = asyncio.create_task(read_requests())
            
            try:
                while not self.done.is_set():
                    try:
                        cmd = await asyncio.wait_for(self.commands_to_send.get(), timeout=0.1)
                        if cmd is None:
                            break
                        yield cmd
                        self.commands_to_send.task_done()
                    except asyncio.TimeoutError:
                        continue
            except asyncio.CancelledError:
                pass
            finally:
                task.cancel()

    async def run_test():
        # Find an open port
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()

        # Start mock gRPC server
        server = grpc.aio.server()
        service = MockTeleRemoteService()
        teleremote_pb2_grpc.add_TeleRemoteServiceServicer_to_server(service, server)
        server.add_insecure_port(f"127.0.0.1:{port}")
        await server.start()

        # Set up client callbacks
        cmd1_called = asyncio.Event()
        cmd2_called = asyncio.Event()
        received_input = ""

        async def handle_cmd1(input_str):
            nonlocal received_input
            received_input = input_str
            cmd1_called.set()

        def handle_cmd2(input_str):
            cmd2_called.set()

        client = TeleClient("IntegrationTestApp", "127.0.0.1", port)
        client.add_action(Action("Cmd1", callback=handle_cmd1))
        client.add_action(Action("Cmd2", callback=handle_cmd2))

        # Start client
        await client.start()
        
        # Wait for registration to reach the server
        for _ in range(30):
            if len(service.registrations) > 0:
                break
            await asyncio.sleep(0.1)

        assert len(service.registrations) == 1
        reg = service.registrations[0]
        assert reg.component_name == "IntegrationTestApp"
        assert reg.host == "127.0.0.1"
        assert reg.port == port
        menu_data = json.loads(reg.registration.menu_json)
        assert menu_data[0]["buttons"][0]["label"] == "Cmd1"

        # Send a telemetry message from client to server
        await client.send_telemetry("Hello Telegram")
        for _ in range(30):
            if len(service.telemetries) > 0:
                break
            await asyncio.sleep(0.1)

        assert service.telemetries == ["Hello Telegram"]

        # Send a command from server to client
        cmd_msg = teleremote_pb2.BotCommand(
            command_type=teleremote_pb2.BotCommand.CUSTOM_COMMAND,
            custom_payload="Cmd1",
            input="some input text"
        )
        await service.commands_to_send.put(cmd_msg)

        # Wait for handler execution
        await asyncio.wait_for(cmd1_called.wait(), timeout=3.0)
        assert received_input == "some input text"

        # Send another command
        cmd_msg_2 = teleremote_pb2.BotCommand(
            command_type=teleremote_pb2.BotCommand.CUSTOM_COMMAND,
            custom_payload="Cmd2",
            input=""
        )
        await service.commands_to_send.put(cmd_msg_2)
        await asyncio.wait_for(cmd2_called.wait(), timeout=3.0)

        # Stop client and server
        await client.close()
        await server.stop(grace=0.1)

    asyncio.run(run_test())
