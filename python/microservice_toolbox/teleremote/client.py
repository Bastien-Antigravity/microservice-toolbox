#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides a resilient, bi-directional gRPC Tele-Remote client matching the Go package design.
Maintains a resilient stream connection to the tele-remote service, manages action registration,
serializes menu configuration to JSON, and dispatches callbacks.

DATA FLOW:
1. User adds/updates actions.
2. Client registers actions to local cache and maps handlers.
3. Client automatically dials target gateway.
4. Client sends Registration ComponentMessage.
5. Client receives stream BotCommand messages, queuing them for background dispatch.

KEY PARAMETERS:
- component_name: Identification string of the component.
- target_ip: IP address of the tele-remote gateway.
- target_port: Port of the tele-remote gateway.
- logger: Logging provider conforming to the project's Logger protocol.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Callable, List, Dict, Optional, Any

import grpc
from microservice_toolbox.logger import Logger, ensure_safe_logger
from .grpc_client import teleremote_pb2, teleremote_pb2_grpc


@dataclass
class Action:
    """Action defines a single interactive element in the Telegram UI."""
    label: str
    sub_menu: List['Action'] = field(default_factory=list)
    input_prompt: str = ""                    # If set, bot asks user for text input
    callback: Optional[Callable[[str], Any]] = None  # Handler receives optional user text


class TeleClient:
    """TeleClient maintains a resilient gRPC connection to tele-remote."""

    def __init__(self, component_name: str, target_ip: str, target_port: int, logger: Optional[Logger] = None):
        self.component_name = component_name
        self.target_ip = target_ip
        self.target_port = target_port
        self.logger = ensure_safe_logger(logger)

        self._actions: List[Action] = []
        self._handlers: Dict[str, Callable[[str], Any]] = {}

        self._conn: Optional[grpc.aio.Channel] = None
        self._stream: Optional[grpc.aio.StreamStreamCall] = None
        self._conn_task: Optional[asyncio.Task] = None
        self._dispatcher_task: Optional[asyncio.Task] = None

        self._cmd_chan = asyncio.Queue(maxsize=100)
        self._closed = False

    def add_action(self, action: Action):
        """registers a new action or sub-menu tree"""
        self._actions.append(action)
        self._register_handlers_recursive(action)

    def update_actions(self, actions: List[Action]):
        """replaces all current actions and handlers"""
        self._actions = list(actions)
        self._handlers.clear()
        for action in self._actions:
            self._register_handlers_recursive(action)

    def _register_handlers_recursive(self, action: Action):
        if action.callback is not None:
            self._handlers[action.label] = action.callback
        for sub in action.sub_menu:
            self._register_handlers_recursive(sub)

    async def start(self):
        """initiates the connection and registration process"""
        loop = asyncio.get_event_loop()
        self._conn_task = loop.create_task(self._connection_manager())
        self._dispatcher_task = loop.create_task(self._command_dispatcher())

    def generate_menu_json(self) -> str:
        """returns the structured JSON representation of the action tree"""
        rows = []
        for action in self._actions:
            btn = self._convert_action_to_btn(action)
            rows.append({"buttons": [btn]})
        return json.dumps(rows)

    def _convert_action_to_btn(self, action: Action) -> Dict[str, Any]:
        btn = {
            "label": action.label,
        }
        if action.input_prompt:
            btn["input_prompt"] = action.input_prompt

        if action.sub_menu or action.callback is None:
            # Recursive Menu Generation - one button per row
            sub_rows = []
            for sub_a in action.sub_menu:
                sub_btn = self._convert_action_to_btn(sub_a)
                sub_rows.append({"buttons": [sub_btn]})
            btn["menu"] = sub_rows
        else:
            # Command Leaf
            btn["cmd_type"] = 99
            btn["payload"] = action.label  # Unique routing key

        return btn

    async def push_menu_update(self):
        """manually triggers the background transmission of the current UI state"""
        if self._stream:
            await self._send_registration(self._stream)

    async def send_telemetry(self, msg: str):
        """streams an arbitrary text message to the Telegram admin chat"""
        if not self._stream:
            raise RuntimeError("not connected to tele-remote")

        payload = teleremote_pb2.ComponentMessage(
            component_name=self.component_name,
            telemetry=msg
        )
        await self._stream.write(payload)

    async def _connection_manager(self):
        addr = f"{self.target_ip}:{self.target_port}"

        while not self._closed:
            self.logger.info(f"TeleClient connecting to {addr}...")
            channel = None
            stream = None
            try:
                # 1. Create channel and connection client
                channel = grpc.aio.insecure_channel(addr)
                self._conn = channel
                client = teleremote_pb2_grpc.TeleRemoteServiceStub(channel)

                # 2. Establish bi-directional stream
                stream = client.Connect()
                self._stream = stream

                # 3. Handshake/Initial registration
                await self._send_registration(stream)
            except Exception as e:
                if not self._closed:
                    self.logger.warning(f"TeleClient stream creation failed: {e}")
                    if channel:
                        try:
                            await channel.close()
                        except Exception:
                            pass
                    self._conn = None
                    self._stream = None
                    await asyncio.sleep(5)
                    continue

            self.logger.info("TeleClient successfully registered with tele-remote")

            # 4. Receive loop
            try:
                async for cmd in stream:
                    if cmd.command_type == teleremote_pb2.BotCommand.REFRESH_MENU:
                        self.logger.info("TeleClient received REFRESH_MENU request")
                        await self._send_registration(stream)
                        continue

                    if self._closed:
                        break

                    try:
                        self._cmd_chan.put_nowait(cmd)
                    except asyncio.QueueFull:
                        self.logger.warning("TeleClient command channel full, dropping command")
            except Exception as e:
                if not self._closed:
                    self.logger.warning(f"TeleClient disconnected from tele-remote: {e}")
            finally:
                await self._disconnect()

            if not self._closed:
                await asyncio.sleep(3)

    async def _send_registration(self, stream):
        menu = self.generate_menu_json()
        reg_msg = teleremote_pb2.ComponentMessage(
            component_name=self.component_name,
            host="127.0.0.1",
            port=self.target_port,
            registration=teleremote_pb2.Registration(menu_json=menu)
        )
        try:
            await stream.write(reg_msg)
        except Exception as e:
            self.logger.error(f"TeleClient failed to send registration: {e}")

    async def _command_dispatcher(self):
        while not self._closed:
            try:
                cmd = await self._cmd_chan.get()
                handler = self._handlers.get(cmd.custom_payload)
                if handler:
                    self.logger.info(f"Executing automatic Tele-Remote command: {cmd.custom_payload} (Input: {cmd.input})")
                    asyncio.create_task(self._run_handler(handler, cmd))
                else:
                    self.logger.warning(f"No handler registered for command payload: {cmd.custom_payload}")
                self._cmd_chan.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in command dispatcher: {e}")

    async def _run_handler(self, handler, cmd):
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(cmd.input)
            else:
                handler(cmd.input)
        except Exception as e:
            self.logger.error(f"Tele-Remote command handler failed: {e}")

    async def _disconnect(self):
        if self._stream:
            try:
                self._stream.cancel()
            except Exception:
                pass
            self._stream = None

        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None

    async def close(self):
        """gracefully stops the client"""
        if self._closed:
            return
        self._closed = True

        await self._disconnect()

        if self._conn_task:
            self._conn_task.cancel()
            try:
                await self._conn_task
            except asyncio.CancelledError:
                pass
            self._conn_task = None

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
            self._dispatcher_task = None
