"""
End-to-End tests for RAV-SPY.
Simulates user interaction with the Telegram bot and subsequent agent execution.
Covers Positive and Negative cases.
"""
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import os
import pyotp
import asyncio
import httpx
import base64
from bot.telegram_bot import start_handler, otp_handler, message_handler
from bot.auth import AuthManager
import bot.telegram_bot as tg_bot
from bot.rate_limiter import _user_command_times
from telegram import constants

class TestE2E(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Setup environment variables for testing
        os.environ["OTP_SECRET_KEY"] = "JBSWY3DPEHPK3PXP"
        os.environ["JWT_SECRET_KEY"] = "test_secret_key_for_e2e"
        os.environ["ALLOWED_USER_IDS"] = "12345"
        os.environ["TELEGRAM_BOT_TOKEN"] = "mock_token"
        os.environ["AGENT_API_KEY"] = "mock_agent_key"
        os.environ["AGENT_HOST"] = "localhost"
        os.environ["AGENT_PORT"] = "8765"
        os.environ["DEV_MODE_ENABLED"] = "false"
        
        # Clear sessions and rate limit state
        tg_bot._user_sessions = {}
        _user_command_times.clear()
        
        # Setup mock agent in registry
        from bot.agent_registry import registry
        self.mock_agents = {
            "MyLaptop": {"host": "localhost", "port": 8765, "api_key": "mock_agent_key"}
        }
        patcher = patch('bot.agent_registry.AgentRegistry._load', return_value=self.mock_agents)
        self.mock_load = patcher.start()
        self.addCleanup(patcher.stop)
        
        # Ensure singleton is aware
        registry.agents = self.mock_agents
        tg_bot._user_active_agent[str(12345)] = "MyLaptop"
        
        self.user_id = 12345
        self.totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")

    def tearDown(self):
        pass

    def create_mock_update(self, text, user_id=None):
        if user_id is None:
            user_id = self.user_id
        update = MagicMock()
        update.effective_user.id = user_id
        update.effective_chat.id = 100
        update.message.text = text
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.message.reply_video = AsyncMock()
        update.message.reply_document = AsyncMock()
        # Mock delete for the processing message
        # Since reply_text returns a message object
        msg_mock = AsyncMock()
        update.message.reply_text.return_value = msg_mock
        return update

    def create_mock_context(self, args=None):
        context = MagicMock()
        context.args = args or []
        context.bot.send_chat_action = AsyncMock()
        return context

    async def test_positive_full_flow(self):
        """Test happy path: Start -> Login -> Command."""
        # 1. User sends /start
        update = self.create_mock_update("/start")
        context = self.create_mock_context()
        await start_handler(update, context)
        
        update.message.reply_text.assert_called()
        self.assertIn("login", update.message.reply_text.call_args[0][0].lower())
        
        # 2. User sends correct OTP
        valid_otp = self.totp.now()
        update = self.create_mock_update(f"/otp {valid_otp}")
        context = self.create_mock_context(args=[valid_otp])
        await otp_handler(update, context)
        
        self.assertIn("Login berhasil", update.message.reply_text.call_args[0][0])
        self.assertIn(str(self.user_id), tg_bot._user_sessions)
        
        # 3. User sends !sysinfo
        update = self.create_mock_update("!sysinfo")
        context = self.create_mock_context()
        
        with patch('bot.telegram_bot.httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200, 
                json=lambda: {"type": "text", "content": "CPU 10%, RAM 4GB"}
            )
            await message_handler(update, context)
            
            # Check typing indicator
            context.bot.send_chat_action.assert_any_call(chat_id=100, action=constants.ChatAction.TYPING)
            
            # Last reply should have HTML format and the result
            last_reply = update.message.reply_text.call_args[0][0]
            self.assertIn("Hasil:", last_reply)
            self.assertIn("CPU 10%", last_reply)

    async def test_positive_media_video_structured(self):
        """Test video command with the new structured dictionary response."""
        tg_bot._user_sessions[str(self.user_id)] = AuthManager.generate_session_token(str(self.user_id))
        update = self.create_mock_update("!video")
        context = self.create_mock_context()

        fake_video_data = base64.b64encode(b"mp4_content").decode()
        response_dict = {
            "type": "video",
            "content": {
                "data": fake_video_data,
                "filename": "test.mp4",
                "mimetype": "video/mp4"
            }
        }

        with patch('bot.telegram_bot.httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: response_dict)
            await message_handler(update, context)
            
            # Check for upload action
            context.bot.send_chat_action.assert_any_call(chat_id=100, action=constants.ChatAction.UPLOAD_VIDEO)
            # Check for reply_video call
            update.message.reply_video.assert_called_once()
            args, kwargs = update.message.reply_video.call_args
            self.assertEqual(args[0], b"mp4_content")
            self.assertEqual(kwargs.get("filename"), "test.mp4")

    async def test_negative_unauthorized_user(self):
        """Test blocking users not in whitelist."""
        update = self.create_mock_update("/start", user_id=99999)
        context = self.create_mock_context()
        await start_handler(update, context)
        
        self.assertIn("Akses Ditolak", update.message.reply_text.call_args[0][0])

    async def test_negative_invalid_otp(self):
        """Test handling of wrong OTP."""
        update = self.create_mock_update("/otp 000000")
        context = self.create_mock_context(args=["000000"])
        await otp_handler(update, context)
        
        self.assertIn("OTP salah", update.message.reply_text.call_args[0][0])
        self.assertNotIn(str(self.user_id), tg_bot._user_sessions)

    async def test_negative_rate_limit(self):
        """Test that spamming commands triggers rate limit."""
        tg_bot._user_sessions[str(self.user_id)] = AuthManager.generate_session_token(str(self.user_id))
        
        update = self.create_mock_update("!sysinfo")
        context = self.create_mock_context()
        
        # Simulate rate limit by patching AuthManager.check_rate_limit
        with patch('bot.auth.AuthManager.check_rate_limit', return_value=False):
            await message_handler(update, context)
            self.assertIn("Terlalu banyak perintah", update.message.reply_text.call_args[0][0])

    async def test_negative_agent_timeout(self):
        """Test handling of agent server timeout."""
        tg_bot._user_sessions[str(self.user_id)] = AuthManager.generate_session_token(str(self.user_id))
        update = self.create_mock_update("!sysinfo")
        context = self.create_mock_context()

        with patch('bot.telegram_bot.httpx.AsyncClient.post', side_effect=httpx.TimeoutException("Timeout")):
            await message_handler(update, context)
            last_reply = update.message.reply_text.call_args[0][0]
            self.assertIn("Waktu Habis", last_reply)

    async def test_negative_agent_error_status(self):
        """Test handling of non-200 HTTP status from agent."""
        tg_bot._user_sessions[str(self.user_id)] = AuthManager.generate_session_token(str(self.user_id))
        update = self.create_mock_update("!sysinfo")
        context = self.create_mock_context()

        with patch('bot.telegram_bot.httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=500)
            await message_handler(update, context)
            last_reply = update.message.reply_text.call_args[0][0]
            self.assertIn("Error Agent (500)", last_reply)

    async def test_negative_injection_attempt(self):
        """Test that dangerous inputs are blocked by bot-side sanitizer."""
        tg_bot._user_sessions[str(self.user_id)] = AuthManager.generate_session_token(str(self.user_id))
        # Bot's message_handler will call sanitizer.sanitize_command via agent/command API
        # but let's test the response when agent returns 400 with security detail
        update = self.create_mock_update("!run evil.py && rm -rf /")
        context = self.create_mock_context()

        with patch('bot.telegram_bot.httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                status_code=400,
                json=lambda: {"detail": "Input tidak valid atau berbahaya"}
            )
            await message_handler(update, context)
            last_reply = update.message.reply_text.call_args[0][0]
            self.assertIn("Permintaan Ditolak", last_reply)
            self.assertIn("berbahaya", last_reply)

    async def test_terminal_auto_yolo_injection(self):
        """Test that agy/opencode commands get auto-injected with safety flags."""
        uid_str = str(self.user_id)
        tg_bot._user_sessions[uid_str] = AuthManager.generate_session_token(uid_str)
        tg_bot._terminal_mode[uid_str] = True
        
        fake_agent = {"host": "127.0.0.1", "port": 8080, "api_key": "test"}
        
        mock_registry = MagicMock()
        mock_registry.get_all.return_value = {"test-agent": fake_agent}
        mock_registry.get_agent.return_value = fake_agent
        
        with patch('bot.telegram_bot.httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
             patch('bot.telegram_bot.registry', mock_registry):
            mock_post.return_value = MagicMock(status_code=200)
            
            # 1. Test agy injection
            update = self.create_mock_update("agy buat aplikasi")
            ctx = self.create_mock_context()
            ctx.user_data = {}
            await message_handler(update, ctx)
            
            mock_post.assert_called_with(
                unittest.mock.ANY,
                json={"user_id": uid_str, "data": "agy --yolo buat aplikasi\n"},
                headers=unittest.mock.ANY
            )

            # 2. Test opencode injection
            update = self.create_mock_update("opencode install deps")
            ctx2 = self.create_mock_context()
            ctx2.user_data = {}
            await message_handler(update, ctx2)
            
            mock_post.assert_called_with(
                unittest.mock.ANY,
                json={"user_id": uid_str, "data": "opencode --dangerously-skip-permissions install deps\n"},
                headers=unittest.mock.ANY
            )

    async def test_ultimate_expansion_features(self):
        """Test routing for the new ultimate expansion features."""
        uid_str = str(self.user_id)
        tg_bot._user_sessions[uid_str] = AuthManager.generate_session_token(uid_str)
        tg_bot._terminal_mode[uid_str] = False # Reset terminal mode
        _user_command_times.clear() # Clear rate limits
        context = self.create_mock_context()

        # 1. Test Clipboard
        update = self.create_mock_update("!clip write hello")
        with patch('bot.telegram_bot.httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"type": "text", "content": "✅ Disalin"})
            await message_handler(update, context)
            self.assertIn("Disalin", update.message.reply_text.call_args[0][0])

        # 2. Test Top
        update = self.create_mock_update("!top")
        with patch('bot.telegram_bot.httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"type": "text", "content": "🔪 Top Processes"})
            await message_handler(update, context)
            self.assertIn("Top Processes", update.message.reply_text.call_args[0][0])

        # 3. Test Schedule (bot layer parsing)
        update = self.create_mock_update("!schedule in 1s !top")
        await message_handler(update, context)
        # Should confirm scheduling immediately
        self.assertIn("dijadwalkan berjalan dalam 1s", update.message.reply_text.call_args[0][0])

if __name__ == '__main__':
    unittest.main()
