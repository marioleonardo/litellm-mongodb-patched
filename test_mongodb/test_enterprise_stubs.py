"""
Tests that enterprise stubs can be imported and provide expected interfaces.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestEnterpriseStubs:
    def test_litellm_enterprise_importable(self):
        import litellm_enterprise
        assert litellm_enterprise is not None

    def test_enterprise_routes_importable(self):
        from litellm_enterprise.proxy.enterprise_routes import router
        assert router is not None

    def test_enterprise_proxy_config(self):
        from litellm_enterprise.proxy.proxy_server import EnterpriseProxyConfig
        config = EnterpriseProxyConfig()
        assert config is not None

    def test_enterprise_custom_auth(self):
        from litellm_enterprise.proxy.auth.user_api_key_auth import enterprise_custom_auth
        assert callable(enterprise_custom_auth)

    def test_enterprise_route_checks(self):
        from litellm_enterprise.proxy.auth.route_checks import EnterpriseRouteChecks
        checks = EnterpriseRouteChecks()
        assert checks is not None

    def test_enterprise_callback_controls(self):
        from litellm_enterprise.enterprise_callbacks.callback_controls import EnterpriseCallbackControls
        ctrl = EnterpriseCallbackControls()
        assert ctrl is not None

    def test_enterprise_guardrails(self):
        from litellm_enterprise.enterprise_callbacks.llama_guard import _ENTERPRISE_LlamaGuard
        from litellm_enterprise.enterprise_callbacks.llm_guard import _ENTERPRISE_LLMGuard
        from litellm_enterprise.enterprise_callbacks.secret_detection import _ENTERPRISE_SecretDetection
        assert _ENTERPRISE_LlamaGuard is not None
        assert _ENTERPRISE_LLMGuard is not None
        assert _ENTERPRISE_SecretDetection is not None

    def test_enterprise_email_stubs(self):
        from litellm_enterprise.enterprise_callbacks.send_emails.base_email import BaseEmailSender
        from litellm_enterprise.enterprise_callbacks.send_emails.resend_email import _ENTERPRISE_ResendEmail
        from litellm_enterprise.enterprise_callbacks.send_emails.sendgrid_email import _ENTERPRISE_SendGridEmail
        from litellm_enterprise.enterprise_callbacks.send_emails.smtp_email import _ENTERPRISE_SMTPEmail
        assert BaseEmailSender is not None
        assert _ENTERPRISE_ResendEmail is not None
        assert _ENTERPRISE_SendGridEmail is not None
        assert _ENTERPRISE_SMTPEmail is not None

    def test_enterprise_sso_handler(self):
        from litellm_enterprise.proxy.auth.custom_sso_handler import EnterpriseCustomSSOHandler
        handler = EnterpriseCustomSSOHandler()
        assert handler is not None

    def test_check_batch_cost(self):
        from litellm_enterprise.proxy.common_utils.check_batch_cost import CheckBatchCost
        obj = CheckBatchCost()
        assert obj is not None

    def test_check_responses_cost(self):
        from litellm_enterprise.proxy.common_utils.check_responses_cost import CheckResponsesCost
        obj = CheckResponsesCost()
        assert obj is not None

    def test_key_management_params(self):
        from litellm_enterprise.proxy.management_endpoints.key_management_endpoints import (
            apply_enterprise_key_management_params
        )
        assert callable(apply_enterprise_key_management_params)


class TestEnterpriseImportsFallback:
    """Verify that the original litellm files handle missing enterprise imports gracefully."""
    
    def test_proxy_hooks_init_enterprise_fallback(self):
        """litellm/proxy/hooks/__init__.py should have a try/except for ENTERPRISE_PROXY_HOOKS."""
        import litellm.proxy.hooks
        # Should not raise ImportError
        assert hasattr(litellm.proxy.hooks, '__file__')

    def test_proxy_server_enterprise_fallback(self):
        """proxy_server.py should handle missing enterprise imports."""
        # Just importing should not raise
        import litellm.proxy.proxy_server
        assert hasattr(litellm.proxy.proxy_server, '__file__')
