#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides a resilient, bi-directional gRPC Tele-Remote client matching the Go package design.
Maintains a resilient stream connection to the tele-remote service, manages action registration,
serializes menu configuration (including OpenMFE priority & ordering) to JSON, enforces TLS/mTLS
and x-tele-auth policies, and dispatches callbacks.

DATA FLOW:
1. User adds/updates actions and optional priority/TLS/auth policy (or configure_from_app_config).
2. Client registers actions to local cache and maps handlers.
3. Client automatically dials target gateway via create_aio_channel (TLS/mTLS or local plaintext).
4. Client opens Connect stream (with optional x-tele-auth metadata) and sends Registration.
5. Client receives stream BotCommand messages, queuing them for background dispatch.

KEY PARAMETERS:
- component_name: Identification string of the component.
- target_ip: IP address of the tele-remote gateway.
- target_port: Port of the tele-remote gateway.
- logger: Logging provider conforming to the project's Logger protocol.
"""

from asyncio import (
    CancelledError as asyncioCancelledError,
    Queue as asyncioQueue,
    QueueFull as asyncioQueueFull,
    Task as asyncioTask,
    create_task as asyncioCreateTask,
    get_event_loop as asyncioGetEventLoop,
    iscoroutinefunction as asyncioIscoroutinefunction,
    sleep as asyncioSleep,
)
from dataclasses import dataclass as dataclassesDataclass, field as dataclassesField
from json import dumps as jsonDumps
from typing import (
    Any as typeAny,
    Callable as typeCallable,
    Dict as typeDict,
    List as typeList,
    Optional as typeOptional,
)

from grpc import aio as grpcAio

from ..config.local_tls import LocalTLSConfig
from ..logger import Logger, ensure_safe_logger
from ..network.tls import create_aio_channel, normalize_tls_mode
from ..wiretap import is_enabled, record_event
from .grpc_client import teleremote_pb2, teleremote_pb2_grpc

# -----------------------------------------------------------------------------------------------


@dataclassesDataclass
class Action:
    """Action defines a single interactive element in the Telegram UI."""

    label: str
    sub_menu: typeList["Action"] = dataclassesField(default_factory=list)
    input_prompt: str = ""  # If set, bot asks user for text input
    callback: typeOptional[typeCallable[[str], typeAny]] = None  # Handler receives optional user text
    order: int = 0


# -----------------------------------------------------------------------------------------------


def _parse_capability_bool(raw: typeAny) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        trimmed = raw.strip().lower()
        if trimmed in ("", "false"):
            return False
        if trimmed == "true":
            return True
        raise ValueError(f"expected boolean or 'true'/'false', got {raw!r}")
    raise ValueError(f"expected boolean or string, got {type(raw).__name__}")


# -----------------------------------------------------------------------------------------------


class TeleClient:
    """TeleClient maintains a resilient gRPC connection to tele-remote."""

    def __init__(
        self,
        component_name: str,
        target_ip: str,
        target_port: int,
        logger: typeOptional[Logger] = None,
    ):
        self.component_name = component_name
        self.target_ip = target_ip
        self.target_port = target_port
        self.logger = ensure_safe_logger(logger)

        self._actions: typeList[Action] = []
        self._handlers: typeDict[str, typeCallable[[str], typeAny]] = {}

        self._conn: typeOptional[grpcAio.Channel] = None
        self._stream: typeOptional[grpcAio.StreamStreamCall] = None
        self._conn_task: typeOptional[asyncioTask] = None
        self._dispatcher_task: typeOptional[asyncioTask] = None

        self._cmd_chan = asyncioQueue(maxsize=100)
        self._closed = False

        # OpenMFE priority & optional Security / Transport Policy
        self._priority: int = 0
        self._auth_token: str = ""
        self._local_tls: LocalTLSConfig = LocalTLSConfig()
        self._tls_enabled: bool = False
        self._tls_mode: str = "auto"
        self._explicit_ssl_credentials = None

    # -------------------------------------------------------------------------------------------

    def set_priority(self, priority: int) -> "TeleClient":
        """Configures the OpenMFE menu priority for this component."""
        self._priority = priority
        return self

    # -------------------------------------------------------------------------------------------

    def set_auth_token(self, token: str) -> "TeleClient":
        """Configures the shared secret sent in outgoing x-tele-auth gRPC metadata."""
        self._auth_token = token.strip() if token else ""
        return self

    # -------------------------------------------------------------------------------------------

    def set_local_tls(self, cfg: LocalTLSConfig) -> "TeleClient":
        """Configures service-private X.509 TLS/mTLS file paths from the local: section."""
        self._local_tls = LocalTLSConfig(
            cert_file=cfg.cert_file.strip(),
            key_file=cfg.key_file.strip(),
            ca_file=cfg.ca_file.strip(),
            verify_client=cfg.verify_client,
        )
        return self

    # -------------------------------------------------------------------------------------------

    def set_tls_policy(self, enabled: bool, mode: str = "auto") -> "TeleClient":
        """Configures local/remote-aware TLS enforcement."""
        self._tls_enabled = bool(enabled)
        self._tls_mode = normalize_tls_mode(mode)
        return self

    # -------------------------------------------------------------------------------------------

    def set_ssl_credentials(self, credentials: typeAny) -> "TeleClient":
        """Configures explicit gRPC ChannelCredentials for the connection."""
        self._explicit_ssl_credentials = credentials
        return self

    # -------------------------------------------------------------------------------------------

    def configure_from_app_config(self, app_config: typeAny, service_key: str) -> "TeleClient":
        """
        Loads local X.509 credentials, fleet tele_remote TLS/auth policy,
        and registers a live-configuration callback to refresh them dynamically at runtime.
        """
        if app_config is None:
            raise ValueError("TeleClient.configure_from_app_config requires non-nil AppConfig")

        self._apply_app_config_policy(app_config, service_key)

        def _on_live_update(_data: typeDict[str, typeAny]) -> None:
            try:
                self._apply_app_config_policy(app_config, service_key)
            except Exception as exc:
                self.logger.warning(f"TeleClient live config refresh failed: {exc}")

        app_config.on_live_conf_update(_on_live_update)
        return self

    # -------------------------------------------------------------------------------------------

    def _apply_app_config_policy(self, app_config: typeAny, service_key: str) -> None:
        tr_cap = app_config.get_capability("tele_remote")
        if not isinstance(tr_cap, dict):
            tr_cap = {}

        try:
            tls_enabled = _parse_capability_bool(tr_cap.get("tls_enabled"))
        except ValueError as exc:
            raise ValueError(f"invalid tele_remote.tls_enabled: {exc}") from exc

        raw_mode = tr_cap.get("tls_mode", "")
        tls_mode = raw_mode if isinstance(raw_mode, str) else ""

        raw_token = tr_cap.get("auth_token", "")
        auth_token = raw_token.strip() if isinstance(raw_token, str) else ""
        if auth_token:
            try:
                auth_token = app_config.decrypt_secret(auth_token)
            except Exception as exc:
                raise ValueError(f"failed to decrypt tele_remote.auth_token: {exc}") from exc

        self.set_local_tls(app_config.get_local_tls_config(service_key))
        self.set_tls_policy(tls_enabled, tls_mode)
        self.set_auth_token(auth_token)

    # -------------------------------------------------------------------------------------------

    def add_action(self, action: Action) -> None:
        """Registers a new action or sub-menu tree."""
        self._actions.append(action)
        self._register_handlers_recursive(action)

    # -------------------------------------------------------------------------------------------

    def update_actions(self, actions: typeList[Action]) -> None:
        """Replaces all current actions and handlers."""
        self._actions = list(actions)
        self._handlers.clear()
        for action in self._actions:
            self._register_handlers_recursive(action)

    # -------------------------------------------------------------------------------------------

    def _register_handlers_recursive(self, action: Action) -> None:
        if action.callback is not None:
            self._handlers[action.label] = action.callback
        for sub in action.sub_menu:
            self._register_handlers_recursive(sub)

    # -------------------------------------------------------------------------------------------

    async def start(self) -> None:
        """Initiates the connection and registration process."""
        loop = asyncioGetEventLoop()
        self._conn_task = loop.create_task(self._connection_manager())
        self._dispatcher_task = loop.create_task(self._command_dispatcher())

    # -------------------------------------------------------------------------------------------

    def generate_menu_json(self) -> str:
        """Returns the structured JSON representation of the action tree."""
        rows = []
        for action in self._actions:
            btn = self._convert_action_to_btn(action)
            row: typeDict[str, typeAny] = {"buttons": [btn]}
            if action.order > 0:
                row["order"] = action.order
            rows.append(row)

        if self._priority > 0:
            return jsonDumps({"priority": self._priority, "rows": rows})

        return jsonDumps(rows)

    # -------------------------------------------------------------------------------------------

    def _convert_action_to_btn(self, action: Action) -> typeDict[str, typeAny]:
        btn: typeDict[str, typeAny] = {
            "label": action.label,
        }
        if action.order > 0:
            btn["order"] = action.order
        if action.input_prompt:
            btn["input_prompt"] = action.input_prompt
        if action.sub_menu or action.callback is None:
            sub_rows = []
            for sub in action.sub_menu:
                sub_btn = self._convert_action_to_btn(sub)
                sub_row: typeDict[str, typeAny] = {"buttons": [sub_btn]}
                if sub.order > 0:
                    sub_row["order"] = sub.order
                sub_rows.append(sub_row)
            btn["menu"] = sub_rows
        else:
            btn["cmd_type"] = 99
            btn["payload"] = action.label
        return btn

    # -------------------------------------------------------------------------------------------

    async def push_menu_update(self) -> None:
        """Pushes the updated dynamic menu JSON over the active gRPC stream when connected."""
        stream = self._stream
        if stream is not None and not self._closed:
            await self._send_registration(stream)

    # -------------------------------------------------------------------------------------------

    async def send_telemetry(self, msg: str) -> None:
        """Streams an arbitrary text message to the Telegram admin chat."""
        if not self._stream:
            raise RuntimeError("not connected to tele-remote")
        payload = teleremote_pb2.ComponentMessage(
            component_name=self.component_name,
            telemetry=msg,
        )
        await self._stream.write(payload)
        if is_enabled():
            record_event(
                source=self.component_name,
                target="tele_remote",
                protocol="GRPC",
                framing="HTTP/2 Protobuf (Stream)",
                channel="teleremote:telemetry",
                category="telemetry",
                direction="outbound",
                payload_summary=msg,
                bytes_count=len(msg),
            )

    # -------------------------------------------------------------------------------------------

    async def _connection_manager(self) -> None:
        addr = f"{self.target_ip}:{self.target_port}"

        while not self._closed:
            self.logger.info(f"TeleClient connecting to {addr}...")
            channel = None
            stream = None
            try:
                # 1. Create channel according to TLS/mTLS policy
                try:
                    channel = create_aio_channel(
                        addr=addr,
                        target_ip=self.target_ip,
                        local_tls=self._local_tls,
                        tls_enabled=self._tls_enabled,
                        tls_mode=self._tls_mode,
                        explicit_credentials=self._explicit_ssl_credentials,
                    )
                except Exception as tls_err:
                    if not self._closed:
                        self.logger.warning(
                            f"TeleClient failed to resolve TLS credentials for {addr}: {tls_err}"
                        )
                        await asyncioSleep(5)
                        continue
                    break

                self._conn = channel
                client = teleremote_pb2_grpc.TeleRemoteServiceStub(channel)

                # 2. Establish bi-directional stream with optional x-tele-auth metadata
                if self._auth_token:
                    stream = client.Connect(metadata=[("x-tele-auth", self._auth_token)])
                else:
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
                    await asyncioSleep(5)
                    continue
                break

            self.logger.info("TeleClient successfully registered with tele-remote")

            # 4. Receive loop
            try:
                async for cmd in stream:
                    if is_enabled():
                        record_event(
                            source="tele_remote",
                            target=self.component_name,
                            protocol="GRPC",
                            framing="HTTP/2 Protobuf (Stream)",
                            channel="teleremote:command",
                            category="command",
                            direction="inbound",
                            payload_summary=getattr(cmd, "custom_payload", "command"),
                            bytes_count=len(getattr(cmd, "custom_payload", "")) + len(getattr(cmd, "input", "")),
                        )
                    if cmd.command_type == teleremote_pb2.BotCommand.REFRESH_MENU:
                        self.logger.info("TeleClient received REFRESH_MENU request")
                        await self._send_registration(stream)
                        continue

                    if self._closed:
                        break

                    try:
                        self._cmd_chan.put_nowait(cmd)
                    except asyncioQueueFull:
                        self.logger.warning("TeleClient command channel full, dropping command")
            except Exception as e:
                if not self._closed:
                    self.logger.warning(f"TeleClient disconnected from tele-remote: {e}")
            finally:
                await self._disconnect()

            if not self._closed:
                await asyncioSleep(3)

    # -------------------------------------------------------------------------------------------

    async def _send_registration(self, stream: typeAny) -> None:
        menu = self.generate_menu_json()
        reg_msg = teleremote_pb2.ComponentMessage(
            component_name=self.component_name,
            host="127.0.0.1",
            port=self.target_port,
            registration=teleremote_pb2.Registration(menu_json=menu),
        )
        try:
            await stream.write(reg_msg)
            if is_enabled():
                record_event(
                    source=self.component_name,
                    target="tele_remote",
                    protocol="GRPC",
                    framing="HTTP/2 Protobuf (Stream)",
                    channel="teleremote:registration",
                    category="registration",
                    direction="outbound",
                    payload_summary="menu_sync",
                    bytes_count=len(menu),
                    conn_delta=1,
                )
        except Exception as e:
            self.logger.error(f"TeleClient failed to send registration: {e}")

    # -------------------------------------------------------------------------------------------

    async def _command_dispatcher(self) -> None:
        while not self._closed:
            try:
                cmd = await self._cmd_chan.get()
                handler = self._handlers.get(cmd.custom_payload)
                if handler:
                    self.logger.info(
                        f"Executing automatic Tele-Remote command: {cmd.custom_payload} (Input: {cmd.input})"
                    )
                    asyncioCreateTask(self._run_handler(handler, cmd))
                else:
                    self.logger.warning(f"No handler registered for command payload: {cmd.custom_payload}")
                self._cmd_chan.task_done()
            except asyncioCancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in command dispatcher: {e}")

    # -------------------------------------------------------------------------------------------

    async def _run_handler(self, handler: typeCallable[[str], typeAny], cmd: typeAny) -> None:
        try:
            if asyncioIscoroutinefunction(handler):
                await handler(cmd.input)
            else:
                handler(cmd.input)
        except Exception as e:
            self.logger.error(f"Tele-Remote command handler failed: {e}")

    # -------------------------------------------------------------------------------------------

    async def _disconnect(self) -> None:
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

    # -------------------------------------------------------------------------------------------

    async def close(self) -> None:
        """Gracefully stops the client."""
        if self._closed:
            return
        self._closed = True

        await self._disconnect()

        if self._conn_task:
            self._conn_task.cancel()
            try:
                await self._conn_task
            except asyncioCancelledError:
                pass
            self._conn_task = None

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncioCancelledError:
                pass
            self._dispatcher_task = None
