"""Blue Alliance webhook handler for real-time event updates."""
import hashlib
import hmac
import json
from typing import Optional

import aiohttp
from aiohttp import web
from discord.ext import commands
from loguru import logger

from dozer.db import DatabaseTable, Pool
from ._utils import Cog


class TBAWebhookSubscription(DatabaseTable):
    """Database table for TBA webhook subscriptions."""
    __tablename__ = 'tba_webhook_subscriptions'
    __uniques__ = ['subscription_url']
    __versions__ = []

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
                subscription_url text PRIMARY KEY,
                event_key text NOT NULL,
                notification_types text[] NOT NULL,
                created_at timestamp NOT NULL DEFAULT NOW(),
                last_notification timestamp
            )
            """)


class TBAWebhookEvent(DatabaseTable):
    """Database table for storing received TBA webhook events."""
    __tablename__ = 'tba_webhook_events'
    __uniques__ = ['id']
    __versions__ = []

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
                id SERIAL PRIMARY KEY,
                message_type text NOT NULL,
                event_key text,
                event_data jsonb NOT NULL,
                received_at timestamp NOT NULL DEFAULT NOW()
            )
            """)
            # Create an index on event_key for efficient lookups
            await conn.execute(f"""
            CREATE INDEX idx_{cls.__tablename__}_event_key 
            ON {cls.__tablename__}(event_key)
            """)


class TBAWebhooks(Cog):
    """
    Handles Blue Alliance webhooks for real-time event updates.
    
    This cog sets up a webhook endpoint that TBA can send notifications to,
    enabling real-time updates for match results, alliance selections, and more.
    """

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.webhook_secret: Optional[str] = bot.config.get('tba', {}).get('webhook_secret')
        self.webhook_port: int = bot.config.get('tba', {}).get('webhook_port', 8080)
        self.webhook_enabled: bool = bot.config.get('tba', {}).get('webhook_enabled', False)
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
        if self.webhook_enabled:
            bot.loop.create_task(self.start_webhook_server())

    async def start_webhook_server(self):
        """Start the aiohttp webhook server."""
        if not self.webhook_enabled:
            logger.info("TBA webhooks are disabled in config")
            return
            
        self.app = web.Application()
        self.app.router.add_post('/tba/webhook', self.handle_webhook)
        self.app.router.add_get('/tba/webhook/health', self.health_check)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.webhook_port)
        await self.site.start()
        
        logger.info(f"TBA webhook server started on port {self.webhook_port}")

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint for monitoring."""
        return web.json_response({'status': 'healthy', 'service': 'tba_webhooks'})

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """
        Handle incoming TBA webhook notifications.
        
        TBA sends webhook notifications with an X-TBA-Signature header for verification.
        """
        try:
            # Read the raw body for signature verification
            body = await request.read()
            
            # Verify the webhook signature if a secret is configured
            if self.webhook_secret:
                signature = request.headers.get('X-TBA-Signature', '')
                if not self._verify_signature(body, signature):
                    logger.warning("Invalid TBA webhook signature received")
                    return web.Response(status=401, text="Invalid signature")
            
            # Parse the JSON payload
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in TBA webhook payload")
                return web.Response(status=400, text="Invalid JSON")
            
            # Process the webhook event
            await self._process_webhook_event(payload)
            
            return web.Response(status=200, text="OK")
            
        except Exception as e:
            logger.error(f"Error processing TBA webhook: {e}")
            return web.Response(status=500, text="Internal server error")

    def _verify_signature(self, body: bytes, signature: str) -> bool:
        """
        Verify the TBA webhook signature.
        
        TBA signs webhooks with HMAC-SHA256 using the webhook secret.
        """
        if not self.webhook_secret:
            return True
            
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)

    async def _process_webhook_event(self, payload: dict):
        """
        Process a webhook event and store it in the database.
        
        TBA webhook payload structure:
        {
            "message_type": "upcoming_match", "match_score_update", "alliance_selection", etc.
            "message_data": {...}
        }
        """
        message_type = payload.get('message_type', 'unknown')
        message_data = payload.get('message_data', {})
        
        # Extract event key if present
        event_key = message_data.get('event_key') or message_data.get('event', {}).get('key')
        
        logger.info(f"Received TBA webhook: {message_type} for event {event_key}")
        
        # Store the webhook event in the database
        if Pool:
            try:
                async with Pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO tba_webhook_events (message_type, event_key, event_data)
                        VALUES ($1, $2, $3)
                        """,
                        message_type, event_key, json.dumps(message_data)
                    )
                    
                    # Update the last notification time for this event
                    await conn.execute(
                        """
                        UPDATE tba_webhook_subscriptions 
                        SET last_notification = NOW()
                        WHERE event_key = $1
                        """,
                        event_key
                    )
            except Exception as e:
                logger.error(f"Error storing TBA webhook event in database: {e}")
        
        # Here you could add additional processing:
        # - Send Discord notifications for important events
        # - Update cached data
        # - Trigger background tasks

    async def subscribe_to_event(self, event_key: str, notification_types: list = None):
        """
        Subscribe to TBA webhooks for a specific event.
        
        Args:
            event_key: The TBA event key (e.g., "2024cmp")
            notification_types: List of notification types to subscribe to
                               (e.g., ["match_score", "alliance_selection"])
        """
        if not self.webhook_enabled:
            logger.warning("Cannot subscribe to TBA webhooks - webhooks are disabled")
            return False
            
        if notification_types is None:
            notification_types = ["match_score", "alliance_selection", "awards"]
        
        # This would need the actual TBA API key and endpoint
        # For now, just store the subscription in the database
        if Pool:
            try:
                async with Pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO tba_webhook_subscriptions 
                        (subscription_url, event_key, notification_types)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (subscription_url) DO UPDATE
                        SET event_key = $2, notification_types = $3
                        """,
                        "https://your-bot-domain.com/tba/webhook",
                        event_key,
                        notification_types
                    )
                logger.info(f"Subscribed to TBA webhooks for event {event_key}")
                return True
            except Exception as e:
                logger.error(f"Error subscribing to TBA webhooks: {e}")
                return False
        
        return False

    async def cog_unload(self):
        """Clean up the webhook server when the cog is unloaded."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("TBA webhook server stopped")


async def setup(bot):
    """Adds the TBA webhooks cog to the bot."""
    await bot.add_cog(TBAWebhooks(bot))
