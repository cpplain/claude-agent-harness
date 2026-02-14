"""
Tests for info module
"""

import json
import unittest
from io import StringIO
from unittest.mock import patch

from agent_harness.info import (
    cmd_info_guide,
    cmd_info_preset,
    cmd_info_schema,
    cmd_info_template,
    get_preset,
    get_template,
    list_presets,
    list_templates,
)


class TestTemplates(unittest.TestCase):
    """Test template functionality."""

    def test_list_templates(self):
        """Test listing all templates."""
        templates = list_templates()
        self.assertIsInstance(templates, list)
        self.assertGreater(len(templates), 0)

        # Check structure
        for t in templates:
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("target_path", t)

        # Check expected templates
        names = [t["name"] for t in templates]
        self.assertIn("config.toml", names)
        self.assertIn("spec.md", names)
        self.assertIn("init.md", names)
        self.assertIn("build.md", names)

    def test_get_template(self):
        """Test getting a specific template."""
        template = get_template("config.toml")
        self.assertIsNotNone(template)
        self.assertEqual(template["name"], "config.toml")
        self.assertIn("description", template)
        self.assertIn("target_path", template)
        self.assertIn("content", template)
        self.assertGreater(len(template["content"]), 0)

    def test_get_template_not_found(self):
        """Test getting a non-existent template."""
        template = get_template("nonexistent.txt")
        self.assertIsNone(template)

    def test_cmd_info_template_list(self):
        """Test template list command."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_template(name=None, list_templates_flag=True, all_templates_flag=False, json_output=False)
            output = fake_out.getvalue()
            self.assertIn("Available Templates", output)
            self.assertIn("config.toml", output)

    def test_cmd_info_template_list_json(self):
        """Test template list command with JSON output."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_template(name=None, list_templates_flag=True, all_templates_flag=False, json_output=True)
            output = fake_out.getvalue()
            data = json.loads(output)
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)

    def test_cmd_info_template_get(self):
        """Test getting a specific template."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_template(name="config.toml", list_templates_flag=False, all_templates_flag=False, json_output=False)
            output = fake_out.getvalue()
            self.assertIn("config.toml", output)
            self.assertIn("Content:", output)

    def test_cmd_info_template_get_json(self):
        """Test getting a specific template as JSON."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_template(name="config.toml", list_templates_flag=False, all_templates_flag=False, json_output=True)
            output = fake_out.getvalue()
            data = json.loads(output)
            self.assertEqual(data["name"], "config.toml")
            self.assertIn("content", data)

    def test_cmd_info_template_no_args(self):
        """Test template command with no arguments."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_template(name=None, list_templates_flag=False, all_templates_flag=False, json_output=False)
            output = fake_out.getvalue()
            self.assertIn("Error", output)

    def test_cmd_info_template_all(self):
        """Test getting all templates with content."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_template(name=None, list_templates_flag=False, all_templates_flag=True, json_output=False)
            output = fake_out.getvalue()
            # Should include all template names
            self.assertIn("config.toml", output)
            self.assertIn("spec.md", output)
            self.assertIn("init.md", output)
            self.assertIn("build.md", output)
            # Should include content markers
            self.assertIn("Content:", output)

    def test_cmd_info_template_all_json(self):
        """Test getting all templates with content as JSON."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_template(name=None, list_templates_flag=False, all_templates_flag=True, json_output=True)
            output = fake_out.getvalue()
            data = json.loads(output)
            self.assertIsInstance(data, list)
            # Should have all templates
            self.assertEqual(len(data), 4)
            # Each should have content
            for template in data:
                self.assertIn("name", template)
                self.assertIn("description", template)
                self.assertIn("target_path", template)
                self.assertIn("content", template)
                self.assertGreater(len(template["content"]), 0)


class TestPresets(unittest.TestCase):
    """Test preset functionality."""

    def test_list_presets(self):
        """Test listing all presets."""
        presets = list_presets()
        self.assertIsInstance(presets, list)
        self.assertGreater(len(presets), 0)

        # Check structure
        for p in presets:
            self.assertIn("name", p)
            self.assertIn("description", p)

        # Check expected presets
        names = [p["name"] for p in presets]
        self.assertIn("python", names)
        self.assertIn("go", names)
        self.assertIn("rust", names)
        self.assertIn("web-nodejs", names)
        self.assertIn("read-only", names)

    def test_get_preset(self):
        """Test getting a specific preset."""
        preset = get_preset("python")
        self.assertIsNotNone(preset)
        self.assertEqual(preset["name"], "python")
        self.assertIn("description", preset)
        self.assertIn("config", preset)
        self.assertIsInstance(preset["config"], dict)

    def test_get_preset_not_found(self):
        """Test getting a non-existent preset."""
        preset = get_preset("nonexistent")
        self.assertIsNone(preset)

    def test_cmd_info_preset_list(self):
        """Test preset list command."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_preset(name=None, list_presets_flag=True, json_output=False)
            output = fake_out.getvalue()
            self.assertIn("Available Presets", output)
            self.assertIn("python", output)

    def test_cmd_info_preset_list_json(self):
        """Test preset list command with JSON output."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_preset(name=None, list_presets_flag=True, json_output=True)
            output = fake_out.getvalue()
            data = json.loads(output)
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)

    def test_cmd_info_preset_get(self):
        """Test getting a specific preset."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_preset(name="python", list_presets_flag=False, json_output=False)
            output = fake_out.getvalue()
            self.assertIn("python", output)
            self.assertIn("Configuration:", output)

    def test_cmd_info_preset_get_json(self):
        """Test getting a specific preset as JSON."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_preset(name="python", list_presets_flag=False, json_output=True)
            output = fake_out.getvalue()
            data = json.loads(output)
            self.assertEqual(data["name"], "python")
            self.assertIn("config", data)


class TestSchema(unittest.TestCase):
    """Test schema functionality."""

    def test_cmd_info_schema(self):
        """Test schema command."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_schema(json_output=False)
            output = fake_out.getvalue()
            self.assertIn("Configuration Schema", output)
            self.assertIn("model", output)

    def test_cmd_info_schema_json(self):
        """Test schema command with JSON output."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_schema(json_output=True)
            output = fake_out.getvalue()
            data = json.loads(output)
            self.assertIsInstance(data, dict)
            self.assertIn("model", data)
            self.assertIn("security", data)
            self.assertIn("tracking", data)
            self.assertIn("phases", data)

            # Check model field structure
            self.assertIn("type", data["model"])
            self.assertIn("description", data["model"])
            self.assertIn("options", data["model"])

            # Check security field structure
            self.assertIn("fields", data["security"])
            self.assertIn("permission_mode", data["security"]["fields"])

            # Check tracking field structure
            self.assertIn("fields", data["tracking"])
            self.assertIn("type", data["tracking"]["fields"])


class TestGuide(unittest.TestCase):
    """Test guide functionality."""

    def test_cmd_info_guide(self):
        """Test guide command."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_guide(json_output=False)
            output = fake_out.getvalue()
            # Should contain some guide content
            self.assertGreater(len(output), 100)

    def test_cmd_info_guide_json(self):
        """Test guide command with JSON output."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_info_guide(json_output=True)
            output = fake_out.getvalue()
            data = json.loads(output)
            self.assertIsInstance(data, dict)
            self.assertIn("title", data)
            self.assertIn("sections", data)
            self.assertIn("content", data)


if __name__ == "__main__":
    unittest.main()
