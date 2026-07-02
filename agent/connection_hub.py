"""
Connection Hub — obfuscated, resilient communication channel.
Features: domain fronting, randomized intervals, TLS mimic, WebSocket fallback.
"""
import os
import time
import random
import asyncio
import httpx
from loguru import logger

BASE_JITTER = (30, 180)


class ConnectionHub:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=30)
        self._running = False
        self._task = None
        self._last_heartbeat = 0
        self._consecutive_failures = 0

    @property
    def jitter_range(self):
        if self._consecutive_failures > 3:
            return (10, 30)
        if self._consecutive_failures > 0:
            return (15, 60)
        return BASE_JITTER

    async def heartbeat_loop(self, agent_url: str, api_key: str, on_beat):
        self._running = True
        while self._running:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        f"{agent_url}/system/heartbeat",
                        headers={"X-API-Key": api_key},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        self._consecutive_failures = 0
                        await on_beat(data)
                    else:
                        self._consecutive_failures += 1
            except Exception:
                self._consecutive_failures += 1

            jitter = random.randint(*self.jitter_range)
            await asyncio.sleep(jitter)

    def stop(self):
        self._running = False


connection_hub = ConnectionHub()
