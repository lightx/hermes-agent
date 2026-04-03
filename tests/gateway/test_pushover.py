"""Tests for the Pushover platform adapter."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from gateway.config import Platform, PlatformConfig
from gateway.platforms.pushover import PushoverAdapter, check_pushover_requirements, MAX_MESSAGE_LENGTH


class TestCheckPushoverRequirements:
    """Test check_pushover_requirements()."""

    def test_missing_both_env_vars(self):
        with patch.dict("os.environ", {}, clear=True):
            assert check_pushover_requirements() is False

    def test_only_app_token(self):
        with patch.dict("os.environ", {"PUSHOVER_APP_TOKEN": "tok", "PUSHOVER_USER_KEY": ""}, clear=True):
            assert check_pushover_requirements() is False

    def test_only_user_key(self):
        with patch.dict("os.environ", {"PUSHOVER_APP_TOKEN": "", "PUSHOVER_USER_KEY": "key"}, clear=True):
            assert check_pushover_requirements() is False

    def test_both_env_vars_set(self):
        with patch.dict("os.environ", {"PUSHOVER_APP_TOKEN": "tok", "PUSHOVER_USER_KEY": "key"}, clear=True):
            assert check_pushover_requirements() is True


class TestPushoverAdapterInit:
    """Test PushoverAdapter initialization."""

    def test_adapter_platform_is_pushover(self):
        config = PlatformConfig(enabled=True)
        adapter = PushoverAdapter(config)
        assert adapter.platform == Platform.PUSHOVER

    def test_adapter_reads_tokens_from_env(self):
        config = PlatformConfig(enabled=True)
        with patch.dict("os.environ", {"PUSHOVER_APP_TOKEN": "my-app-token", "PUSHOVER_USER_KEY": "my-user-key"}, clear=True):
            adapter = PushoverAdapter(config)
            assert adapter._app_token == "my-app-token"
            assert adapter._user_key == "my-user-key"

    def test_adapter_reads_device_from_config_extra(self):
        config = PlatformConfig(enabled=True, extra={"device": "my-phone"})
        adapter = PushoverAdapter(config)
        assert adapter._device == "my-phone"

    def test_adapter_empty_device_when_not_set(self):
        config = PlatformConfig(enabled=True)
        adapter = PushoverAdapter(config)
        assert adapter._device == ""


class TestPushoverAdapterSend:
    """Test PushoverAdapter.send()."""

    @pytest.fixture
    def adapter(self):
        config = PlatformConfig(enabled=True)
        with patch.dict("os.environ", {"PUSHOVER_APP_TOKEN": "tok", "PUSHOVER_USER_KEY": "user"}, clear=True):
            return PushoverAdapter(config)

    @pytest.mark.asyncio
    async def test_send_success(self, adapter):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"status": 1, "request": "req-abc123"})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await adapter.send("user", "Hello world")

        assert result.success is True
        assert result.message_id == "req-abc123"

    @pytest.mark.asyncio
    async def test_send_api_error(self, adapter):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"status": 0, "errors": ["invalid token"]})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await adapter.send("user", "Hello world")

        assert result.success is False
        assert "invalid token" in result.error

    @pytest.mark.asyncio
    async def test_send_http_error(self, adapter):
        with patch("aiohttp.ClientSession") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter.send("user", "Hello world")

        assert result.success is False
        assert "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_send_missing_credentials(self):
        config = PlatformConfig(enabled=True)
        with patch.dict("os.environ", {}, clear=True):
            adapter = PushoverAdapter(config)
            result = await adapter.send("user", "Hello")
        assert result.success is False
        assert "not configured" in result.error


class TestPushoverMessageTruncation:
    """Test message truncation."""

    @pytest.fixture
    def adapter(self):
        config = PlatformConfig(enabled=True)
        with patch.dict("os.environ", {"PUSHOVER_APP_TOKEN": "tok", "PUSHOVER_USER_KEY": "user"}, clear=True):
            return PushoverAdapter(config)

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 1024

    @pytest.mark.asyncio
    async def test_truncates_long_message(self, adapter):
        long_text = "x" * 1100  # exceeds 1024

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"status": 1, "request": "req-abc"})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await adapter.send("user", long_text)

        assert result.success is True
        # Verify the message sent was truncated
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert len(call_args[1]["data"]["message"]) <= 1024
        assert call_args[1]["data"]["message"].endswith("...")


class TestPushoverGetChatInfo:
    """Test get_chat_info()."""

    def test_returns_user_key_as_name(self):
        config = PlatformConfig(enabled=True)
        with patch.dict("os.environ", {"PUSHOVER_APP_TOKEN": "tok", "PUSHOVER_USER_KEY": "my-user"}, clear=True):
            adapter = PushoverAdapter(config)
            info = adapter.get_chat_info("any-chat-id")
        assert info["name"] == "Pushover"
        assert info["type"] == "user"
        assert info["chat_id"] == "my-user"


class TestPushoverSendImage:
    """Test send_image()."""

    @pytest.fixture
    def adapter(self):
        config = PlatformConfig(enabled=True)
        with patch.dict("os.environ", {"PUSHOVER_APP_TOKEN": "tok", "PUSHOVER_USER_KEY": "user"}, clear=True):
            return PushoverAdapter(config)

    @pytest.mark.asyncio
    async def test_send_image_falls_back_to_text(self, adapter):
        """Pushover doesn't support native image send, so it falls back to caption + URL as text."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"status": 1, "request": "req-abc"})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await adapter.send_image("user", "https://example.com/image.jpg", "Look at this")

        assert result.success is True
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        # Verifies caption and URL are concatenated as fallback text
        assert "Look at this" in call_args[1]["data"]["message"]
        assert "https://example.com/image.jpg" in call_args[1]["data"]["message"]
