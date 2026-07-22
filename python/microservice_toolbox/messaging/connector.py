#!/usr/bin/env python
# coding:utf-8

import nats
from typing import Optional
from microservice_toolbox.logger import Logger, ensure_safe_logger
from .config import NatsConfig

async def connect(cfg: NatsConfig, logger: Optional[Logger] = None) -> nats.NATS:
	"""
	Establishes an asynchronous connection to the NATS server and configures event logging.
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

	nc = await nats.connect(
		servers=cfg.servers,
		name=cfg.client_id,
		connect_timeout=cfg.connect_timeout,
		reconnect_time_wait=cfg.reconnect_wait,
		max_reconnect_attempts=cfg.max_reconnects,
		disconnected_cb=disconnected_cb,
		reconnected_cb=reconnected_cb,
		closed_cb=closed_cb,
	)

	log.info(f"[{cfg.client_id}] Successfully connected to NATS at {nc.connected_url}")
	return nc
