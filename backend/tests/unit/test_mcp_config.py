"""
Test cases for MCP configuration module.
"""

import unittest
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch, PropertyMock
from src.agent.config.mcp_config import (
    MCPServerDefinition,
    MCPConfig,
    load_mcp_config,
    DEFAULT_MCP_CONFIG
)


class TestMCPServerDefinition(unittest.TestCase):
    """Test cases for MCPServerDefinition model."""
    
    def test_create_stdio_server(self):
        """Test creating a stdio server definition."""
        server = MCPServerDefinition(
            name="test",
            server_type="stdio",
            command="npx",
            args=["@test/server"],
            env={"API_KEY": "test123"},
            enabled=True,
            description="Test server"
        )
        
        self.assertEqual(server.name, "test")
        self.assertEqual(server.server_type, "stdio")
        self.assertEqual(server.command, "npx")
        self.assertEqual(server.args, ["@test/server"])
        self.assertEqual(server.env, {"API_KEY": "test123"})
        self.assertTrue(server.enabled)
        
    def test_create_http_server(self):
        """Test creating an HTTP server definition."""
        server = MCPServerDefinition(
            name="api",
            server_type="http",
            url="http://localhost:8080",
            enabled=True
        )
        
        self.assertEqual(server.name, "api")
        self.assertEqual(server.server_type, "http")
        self.assertEqual(server.url, "http://localhost:8080")
        self.assertTrue(server.enabled)
        
    def test_default_values(self):
        """Test default values for server definition."""
        server = MCPServerDefinition(
            name="minimal",
            server_type="stdio"
        )
        
        self.assertEqual(server.args, [])
        self.assertEqual(server.env, {})
        self.assertTrue(server.enabled)
        self.assertTrue(server.auto_reconnect)


class TestMCPConfig(unittest.TestCase):
    """Test cases for MCPConfig model."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_config.yaml"
        
    def tearDown(self):
        """Clean up test environment."""
        if self.config_file.exists():
            self.config_file.unlink()
        os.rmdir(self.temp_dir)
        
    def test_default_config(self):
        """Test default configuration values."""
        config = MCPConfig()
        
        self.assertEqual(config.servers, [])
        self.assertTrue(config.auto_discover)
        self.assertEqual(config.refresh_interval, 300)
        self.assertEqual(config.max_tool_rounds, 10)
        self.assertTrue(config.router_enabled)
        self.assertTrue(config.planner_enabled)
        self.assertFalse(config.worker_enabled)
        
    def test_from_yaml(self):
        """Test loading configuration from YAML file."""
        yaml_content = """
servers:
  - name: github
    server_type: stdio
    command: npx
    args:
      - "@modelcontextprotocol/server-github"
    enabled: true
    description: GitHub server

router_enabled: false
planner_enabled: true
"""
        self.config_file.write_text(yaml_content)
        
        config = MCPConfig.from_yaml(self.config_file)
        
        self.assertEqual(len(config.servers), 1)
        self.assertEqual(config.servers[0].name, "github")
        self.assertFalse(config.router_enabled)
        self.assertTrue(config.planner_enabled)
        
    def test_env_variable_substitution(self):
        """Test environment variable substitution in YAML."""
        yaml_content = """
servers:
  - name: api
    server_type: http
    url: "${API_URL}"
    env:
      TOKEN: "${API_TOKEN}"
"""
        self.config_file.write_text(yaml_content)
        
        with patch.dict(os.environ, {
            "API_URL": "http://test.com",
            "API_TOKEN": "secret123"
        }):
            config = MCPConfig.from_yaml(self.config_file)
            
            self.assertEqual(config.servers[0].url, "http://test.com")
            self.assertEqual(config.servers[0].env["TOKEN"], "secret123")
            
    def test_from_env(self):
        """Test creating configuration from environment variables."""
        with patch.dict(os.environ, {
            "GITHUB_PERSONAL_ACCESS_TOKEN": "test_token",
            "MCP_GITHUB_ENABLED": "true",
            "MCP_FILESYSTEM_ENABLED": "true",
            "MCP_FILESYSTEM_ROOT": "/test/path",
            "MCP_ROUTER_ENABLED": "false"
        }):
            config = MCPConfig.from_env()
            
            # Should have github and filesystem servers
            self.assertEqual(len(config.servers), 2)
            server_names = [s.name for s in config.servers]
            self.assertIn("github", server_names)
            self.assertIn("filesystem", server_names)
            
            # Check filesystem configuration
            fs_server = next(s for s in config.servers if s.name == "filesystem")
            self.assertIn("/test/path", fs_server.args)
            
            # Check router is disabled
            self.assertFalse(config.router_enabled)
            
    def test_custom_servers_from_env(self):
        """Test loading custom servers from environment JSON."""
        custom_servers = [
            {
                "name": "custom1",
                "server_type": "http",
                "url": "http://custom1.com",
                "enabled": True
            },
            {
                "name": "custom2",
                "server_type": "websocket",
                "url": "ws://custom2.com",
                "enabled": False
            }
        ]
        
        with patch.dict(os.environ, {
            "MCP_CUSTOM_SERVERS": json.dumps(custom_servers)
        }):
            config = MCPConfig.from_env()
            
            # Find custom servers
            custom1 = next((s for s in config.servers if s.name == "custom1"), None)
            custom2 = next((s for s in config.servers if s.name == "custom2"), None)
            
            self.assertIsNotNone(custom1)
            self.assertEqual(custom1.url, "http://custom1.com")
            self.assertTrue(custom1.enabled)
            
            self.assertIsNotNone(custom2)
            self.assertEqual(custom2.url, "ws://custom2.com")
            self.assertFalse(custom2.enabled)
            
    def test_merge_with_env(self):
        """Test merging YAML config with environment variables."""
        yaml_content = """
servers:
  - name: github
    server_type: stdio
    command: old_command
    enabled: false
  - name: filesystem
    server_type: stdio
    enabled: true

router_enabled: true
planner_enabled: false
"""
        self.config_file.write_text(yaml_content)
        
        config = MCPConfig.from_yaml(self.config_file)
        
        with patch.dict(os.environ, {
            "GITHUB_PERSONAL_ACCESS_TOKEN": "new_token",
            "MCP_GITHUB_ENABLED": "true",
            "MCP_ROUTER_ENABLED": "false",
            "MCP_PLANNER_ENABLED": "true"
        }):
            config = config.merge_with_env()
            
            # GitHub server should be replaced with env version
            github_server = next(s for s in config.servers if s.name == "github")
            self.assertEqual(github_server.env.get("GITHUB_PERSONAL_ACCESS_TOKEN"), "new_token")
            
            # Flags should be overridden
            self.assertFalse(config.router_enabled)
            self.assertTrue(config.planner_enabled)
            
    def test_load_mcp_config_with_file(self):
        """Test load_mcp_config with existing YAML file."""
        yaml_content = """
servers:
  - name: test_server
    server_type: http
    url: "http://test.com"
"""
        self.config_file.write_text(yaml_content)
        
        # Mock environment to prevent additional servers being added
        # We need to explicitly set MCP_FILESYSTEM_ENABLED to false
        with patch.dict(os.environ, {
            'MCP_FILESYSTEM_ENABLED': 'false',
            'GITHUB_TOKEN': ''
        }, clear=True):
            config = load_mcp_config(self.config_file)
            
            self.assertEqual(len(config.servers), 1)
            self.assertEqual(config.servers[0].name, "test_server")
        
    def test_load_mcp_config_no_file(self):
        """Test load_mcp_config when no file exists."""
        # When no file exists and no env vars, should use defaults
        config = load_mcp_config(Path("nonexistent.yaml"))
        
        # Should have default filesystem server
        self.assertEqual(len(config.servers), 1)
        self.assertEqual(config.servers[0].name, "filesystem")
        
    def test_load_mcp_config_env_only(self):
        """Test load_mcp_config with only environment variables."""
        with patch.dict(os.environ, {
            "GITHUB_PERSONAL_ACCESS_TOKEN": "test_token",
            "MCP_GITHUB_ENABLED": "true"
        }):
            config = load_mcp_config(Path("nonexistent.yaml"))
            
            # Should have github server from env
            server_names = [s.name for s in config.servers]
            self.assertIn("github", server_names)


class TestIntegrationWithSettings(unittest.TestCase):
    """Test integration with settings module."""
    
    def test_settings_mcp_properties(self):
        """Test MCP properties in settings."""
        from src.agent.config.settings import AgentSettings
        
        # Create settings with mcp_enabled
        settings = AgentSettings(mcp_enabled=True)
        
        # Mock the mcp_config property
        mock_config = MCPConfig(
            router_enabled=True,
            planner_enabled=False,
            worker_enabled=True
        )
        
        with patch.object(type(settings), 'mcp_config', new_callable=PropertyMock) as mock_prop:
            mock_prop.return_value = mock_config
            
            # Test property accessors
            self.assertTrue(settings.mcp_router_enabled)
            self.assertFalse(settings.mcp_planner_enabled)
            self.assertTrue(settings.mcp_worker_enabled)
        
    @patch("src.agent.config.mcp_config.load_mcp_config")
    def test_settings_mcp_disabled(self, mock_load):
        """Test MCP properties when MCP is globally disabled."""
        mock_config = MCPConfig(
            router_enabled=True,
            planner_enabled=True,
            worker_enabled=True
        )
        mock_load.return_value = mock_config
        
        from src.agent.config.settings import AgentSettings
        
        settings = AgentSettings(mcp_enabled=False)
        
        # All should be False when MCP is disabled
        self.assertFalse(settings.mcp_router_enabled)
        self.assertFalse(settings.mcp_planner_enabled)
        self.assertFalse(settings.mcp_worker_enabled)


if __name__ == "__main__":
    unittest.main()