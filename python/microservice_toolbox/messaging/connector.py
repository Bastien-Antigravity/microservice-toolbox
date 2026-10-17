#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Asynchronous client connector establishing robust NATS connections with lifecycle event logging.

DATA FLOW:
1. Input: NatsConfig specifying cluster endpoints and reconnect parameters.
2. Logic: Initiates async connection with disconnected, reconnected, and closed callbacks.
3. Output: Active nats.NATS connection instance.

KEY PARAMETERS:
- cfg: Validated NatsConfig instance with server addresses and reconnect policies.
- logger: Optional Logger instance for logging lifecycle connection events.
"""

from ssl import (
    CERT_NONE as sslCERT_NONE,
    Purpose as sslPurpose,
    SSLContext as sslSSLContext,
    create_default_context as sslCreateDefaultContext,
)
from typing import Optional

from nats import NATS as natsNATS, connect as natsConnect

from ..logger import Logger, ensure_safe_logger
from .config import NatsConfig

# -----------------------------------------------------------------------------------------------
# ### NATS CONNECTOR ###
# -----------------------------------------------------------------------------------------------


async def connect(cfg: NatsConfig, logger: Optional[Logger] = None) -> natsNATS:
    """
    Establishes an asynchronous connection to the NATS server and configures event logging.

    Args:
        cfg: Validated NATS configuration containing server endpoints and reconnect policies.
        logger: Optional logger for connection state events.

    Returns:
        natsNATS: An active, connected NATS client.

    Raises:
        ValueError: If no NATS servers are configured.
    """
    log = ensure_safe_logger(logger)

    if not cfg.servers:
        raise ValueError("no nats servers configured")

    async def disconnected_cb():
        log.warning(f"[{cfg.client_id}] NATS disconnected, attempting reconnect...")

    async def reconnected_cb():
        log.info(f"[{cfg.client_id}] NATS successfully reconnected")

    async def closed_cb():
        log.error(f"[{cfg.client_id}] NATS connection closed unexpectedly")

    tls_ctx: Optional[sslSSLContext] = None
    has_tls_scheme = any(s.lower().startswith("tls://") for s in cfg.servers)
    if (cfg.tls and cfg.tls.enabled) or has_tls_scheme:
        tls_ctx = sslCreateDefaultContext(
            purpose=sslPurpose.SERVER_AUTH,
            cafile=cfg.tls.ca_file if (cfg.tls and cfg.tls.ca_file) else None
        )
        if cfg.tls and cfg.tls.insecure_skip_verify:
            tls_ctx.check_hostname = False
            tls_ctx.verify_mode = sslCERT_NONE
        if cfg.tls and cfg.tls.cert_file and cfg.tls.key_file:
            tls_ctx.load_cert_chain(certfile=cfg.tls.cert_file, keyfile=cfg.tls.key_file)

    connect_kwargs = {
        "servers": cfg.servers,
        "name": cfg.client_id,
        "connect_timeout": cfg.connect_timeout,
        "reconnect_time_wait": cfg.reconnect_wait,
        "max_reconnect_attempts": cfg.max_reconnects,
        "disconnected_cb": disconnected_cb,
        "reconnected_cb": reconnected_cb,
        "closed_cb": closed_cb,
    }
    if tls_ctx is not None:
        connect_kwargs["tls"] = tls_ctx

    nc = await natsConnect(**connect_kwargs)

    log.info(f"[{cfg.client_id}] Successfully connected to NATS at {nc.connected_url}")
    return nc
