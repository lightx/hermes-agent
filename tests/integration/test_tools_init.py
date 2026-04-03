"""
Integration test: tools/__init__.py import safety.

This test verifies that:
1. Importing the ``tools`` package at various points in the startup sequence
   does not break anything.
2. Pushover integration is importable, correctly wired, and env-isolated.

The Pushover credential tests use monkeypatch to ensure they run identically
whether or not PUSHOVER_APP_TOKEN / PUSHOVER_USER_KEY are set in the shell env.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on the path (mirrors conftest.py)
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Tools import safety
# ─────────────────────────────────────────────────────────────────────────────

class TestToolsImportSafety:
    """Verify tools/__init__.py imports don't break the startup path."""

    def test_tools_import_after_hermes_config(self):
        """
        Import hermes_cli.config first, then import tools.
        This mirrors: hermes config is loaded → CLI command does `import tools`.

        All tools submodule re-exports must be accessible.
        """
        import hermes_cli.config

        import tools

        # Verify the key re-exports are accessible
        assert hasattr(tools, "terminal_tool"), "tools.terminal_tool not re-exported"
        assert hasattr(tools, "browser_tool"), "tools.browser_tool not re-exported"
        assert hasattr(tools, "delegate_tool"), "tools.delegate_tool not re-exported"
        assert hasattr(tools, "vision_tools"), "tools.vision_tools not re-exported"
        assert hasattr(tools, "skills_tool"), "tools.skills_tool not re-exported"
        assert hasattr(tools, "skill_manager_tool"), "tools.skill_manager_tool not re-exported"

        # __all__ function works
        assert callable(tools.check_file_requirements)

    def test_tools_submodule_imports_via_package(self):
        """Verify submodules are accessible via the package re-exports."""
        import tools

        # These are re-exported at package level
        assert callable(tools.terminal_tool)
        assert callable(tools.browser_navigate)  # from browser_tool
        assert callable(tools.delegate_task)  # from delegate_tool
        assert callable(tools.vision_analyze_tool)  # from vision_tools

    def test_check_file_requirements_callable(self):
        """Verify the tools package-level helper is callable without crashing."""
        import tools

        try:
            result = tools.check_file_requirements()
            # Returns bool or None depending on backend availability
            assert result is None or isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"check_file_requirements() raised: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Pushover integration
# ─────────────────────────────────────────────────────────────────────────────

class TestPushoverIntegration:
    """
    Verify Pushover platform integration is correctly wired.

    Tests are env-isolated: they unset PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY
    before running so results are identical in any shell environment.
    """

    @pytest.fixture(autouse=True)
    def _isolate_pushover_env(self, monkeypatch):
        """Remove Pushover env vars so tests are hermetic regardless of shell env."""
        monkeypatch.delenv("PUSHOVER_APP_TOKEN", raising=False)
        monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)

    def test_pushover_adapter_importable(self):
        """PushoverAdapter and check_pushover_requirements must be importable."""
        from gateway.platforms.pushover import (
            PushoverAdapter,
            check_pushover_requirements,
            MAX_MESSAGE_LENGTH,
        )

        assert MAX_MESSAGE_LENGTH == 1024
        assert check_pushover_requirements() is False

    def test_pushover_adapter_instantiable_without_credentials(self):
        """PushoverAdapter can be instantiated even without credentials set."""
        from gateway.platforms.pushover import PushoverAdapter
        from gateway.config import PlatformConfig

        config = PlatformConfig()
        adapter = PushoverAdapter(config)
        assert adapter._app_token == ""
        assert adapter._user_key == ""

    def test_pushover_adapter_send_returns_error_without_credentials(self):
        """PushoverAdapter.send() returns an error SendResult when credentials are missing."""
        import asyncio
        from gateway.platforms.pushover import PushoverAdapter
        from gateway.config import PlatformConfig

        config = PlatformConfig()
        adapter = PushoverAdapter(config)

        result = asyncio.get_event_loop().run_until_complete(
            adapter.send("fake_chat_id", "test message")
        )

        assert result.success is False
        assert "not configured" in result.error

    def test_pushover_send_message_helper_signature(self):
        """Verify tools/send_message_tool _send_pushover has the right signature."""
        from tools.send_message_tool import _send_pushover
        import inspect

        sig = inspect.signature(_send_pushover)
        params = list(sig.parameters.keys())
        assert params == ["token", "user_key", "message"], (
            f"_send_pushover signature changed: {params}"
        )

    def test_pushover_platform_enum(self):
        """Verify Platform.PUSHOVER exists and maps to 'pushover'."""
        from gateway.config import Platform

        assert Platform.PUSHOVER.value == "pushover"

    def test_pushover_env_override_assigns_correct_fields(self):
        """
        Simulate PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY being set and verify
        _apply_env_overrides correctly maps them to the PlatformConfig fields.

        Pushover API: token=PUSHOVER_APP_TOKEN (app token), user=PUSHOVER_USER_KEY (user key).
        _apply_env_overrides must set: .token = PUSHOVER_APP_TOKEN, .api_key = PUSHOVER_USER_KEY.
        """
        from gateway.config import GatewayConfig, Platform, _apply_env_overrides

        config = GatewayConfig()
        with patch.dict(
            os.environ,
            {"PUSHOVER_APP_TOKEN": "my_app_token_abc", "PUSHOVER_USER_KEY": "my_user_key_xyz"},
            clear=False,
        ):
            _apply_env_overrides(config)

        assert Platform.PUSHOVER in config.platforms
        pushover_cfg = config.platforms[Platform.PUSHOVER]
        assert pushover_cfg.enabled is True
        assert pushover_cfg.token == "my_app_token_abc", (
            "token should be PUSHOVER_APP_TOKEN (app token)"
        )
        assert pushover_cfg.api_key == "my_user_key_xyz", (
            "api_key should be PUSHOVER_USER_KEY (user key)"
        )

