"""
Tests for YAML validation, formatting, and parsing.

Makes sure the code editor can properly handle YAML configs - catching errors,
formatting nicely, and converting between YAML and Python dicts.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
from core.code_editor import (
    dict_to_yaml,
    extract_widget_options,
    format_yaml,
    parse_yaml,
    validate_yaml,
)


class TestValidateYaml:
    """Make sure YAML validation catches errors."""

    def test_valid_yaml(self):
        """Valid YAML should pass without errors."""
        yaml_text = """
name: test
value: 123
nested:
  key: value
"""
        is_valid, errors = validate_yaml(yaml_text)
        assert is_valid is True
        assert errors == []

    def test_empty_string(self):
        """Empty string is valid."""
        is_valid, errors = validate_yaml("")
        assert is_valid is True
        assert errors == []

    def test_whitespace_only(self):
        """Just whitespace is fine too."""
        is_valid, errors = validate_yaml("   \n\n   ")
        assert is_valid is True
        assert errors == []

    def test_tabs_not_allowed(self):
        """Tabs should trigger an error."""
        yaml_text = "name:\tvalue"
        is_valid, errors = validate_yaml(yaml_text)
        assert is_valid is False
        assert len(errors) >= 1
        assert any("Tabs" in e.message for e in errors)

    def test_invalid_yaml_syntax(self):
        """Bad YAML syntax should be caught."""
        yaml_text = """
name: test
  bad_indent: value
"""
        is_valid, errors = validate_yaml(yaml_text)
        assert is_valid is False
        assert len(errors) >= 1

    def test_duplicate_keys(self):
        """Having the same key twice is an error."""
        yaml_text = """
name: first
name: second
"""
        is_valid, errors = validate_yaml(yaml_text)
        assert is_valid is False

    def test_complex_valid_yaml(self):
        """Make sure complex nested YAML works."""
        yaml_text = """
widget:
  type: "yasb.clock.ClockWidget"
  options:
    label: "{%H:%M}"
    callbacks:
      on_left: "toggle"
    list_items:
      - item1
      - item2
"""
        is_valid, errors = validate_yaml(yaml_text)
        assert is_valid is True
        assert errors == []


class TestFormatYaml:
    """YAML formatting tests."""

    def test_format_simple_yaml(self):
        """Should format simple YAML nicely."""
        yaml_text = "name: test\nvalue: 123"
        result, error = format_yaml(yaml_text)
        assert error is None
        assert "name:" in result
        assert "value:" in result

    def test_format_empty_string(self):
        """Empty in, empty out."""
        result, error = format_yaml("")
        assert error is None
        assert result == ""

    def test_format_preserves_structure(self):
        """Make sure formatting doesn't change the actual data."""
        yaml_text = """
options:
  label: test
  nested:
    key: value
"""
        result, error = format_yaml(yaml_text)
        assert error is None
        parsed, _ = parse_yaml(result)
        assert parsed["options"]["label"] == "test"
        assert parsed["options"]["nested"]["key"] == "value"

    def test_format_invalid_yaml_returns_original(self):
        """If YAML is broken, just return it unchanged with an error."""
        yaml_text = "invalid: yaml:\n  bad: indent"
        result, error = format_yaml(yaml_text)
        assert error is not None
        assert result == yaml_text

    def test_format_adds_trailing_newline(self):
        """Formatted YAML should end with a newline."""
        yaml_text = "name: test"
        result, error = format_yaml(yaml_text)
        assert error is None
        assert result.endswith("\n")


class TestParseYaml:
    """YAML to dict conversion."""

    def test_parse_simple_yaml(self):
        """Basic YAML parsing."""
        yaml_text = "name: test\nvalue: 123"
        result, error = parse_yaml(yaml_text)
        assert error is None
        assert result == {"name": "test", "value": 123}

    def test_parse_empty_string(self):
        """Empty string becomes empty dict."""
        result, error = parse_yaml("")
        assert error is None
        assert result == {}

    def test_parse_whitespace_only(self):
        """Just whitespace also becomes empty dict."""
        result, error = parse_yaml("   \n\n   ")
        assert error is None
        assert result == {}

    def test_parse_nested_yaml(self):
        """Handle nested structures properly."""
        yaml_text = """
widget:
  type: "yasb.clock.ClockWidget"
  options:
    label: "{%H:%M}"
"""
        result, error = parse_yaml(yaml_text)
        assert error is None
        assert result["widget"]["type"] == "yasb.clock.ClockWidget"
        assert result["widget"]["options"]["label"] == "{%H:%M}"

    def test_parse_list_yaml(self):
        """Lists should work too."""
        yaml_text = """
items:
  - first
  - second
  - third
"""
        result, error = parse_yaml(yaml_text)
        assert error is None
        assert result["items"] == ["first", "second", "third"]

    def test_parse_invalid_yaml(self):
        """Broken YAML returns None with an error."""
        yaml_text = "invalid: yaml:\n  bad"
        result, error = parse_yaml(yaml_text)
        assert result is None
        assert error is not None

    def test_parse_non_dict_yaml(self):
        """We need a dict/mapping, not a list."""
        yaml_text = "- item1\n- item2"
        result, error = parse_yaml(yaml_text)
        assert result is None
        assert "dictionary" in error.lower() or "mapping" in error.lower()


class TestDictToYaml:
    """Converting Python dicts back to YAML."""

    def test_simple_dict(self):
        """Basic dict to YAML."""
        data = {"name": "test", "value": 123}
        result = dict_to_yaml(data)
        assert "name: test" in result
        assert "value: 123" in result

    def test_empty_dict(self):
        """Empty dict becomes empty string."""
        result = dict_to_yaml({})
        assert result == ""

    def test_nested_dict(self):
        """Nested dicts should work."""
        data = {"outer": {"inner": "value"}}
        result = dict_to_yaml(data)
        assert "outer:" in result
        assert "inner: value" in result

    def test_dict_with_list(self):
        """Dicts containing lists should work too."""
        data = {"items": ["a", "b", "c"]}
        result = dict_to_yaml(data)
        assert "items:" in result
        assert "- a" in result

    def test_roundtrip(self):
        """Converting dict -> YAML -> dict should give us back the original."""
        original = {
            "widget": {
                "type": "yasb.clock.ClockWidget",
                "options": {"label": "{%H:%M}", "items": [1, 2, 3]},
            }
        }
        yaml_str = dict_to_yaml(original)
        parsed, error = parse_yaml(yaml_str)
        assert error is None
        assert parsed == original


class TestExtractWidgetOptions:
    """Extracting just the options part from widget configs."""

    def test_extract_from_full_widget(self):
        """Pull options from a complete widget definition."""
        yaml_text = """
type: "yasb.clock.ClockWidget"
options:
  label: "{%H:%M}"
  timezones: []
"""
        parsed, _ = parse_yaml(yaml_text)
        result, error = extract_widget_options(parsed)
        assert error is None
        assert result["label"] == "{%H:%M}"
        assert result["timezones"] == []

    def test_extract_from_named_widget(self):
        """Extract from widget with a name wrapper."""
        yaml_text = """
clock_widget:
  type: "yasb.clock.ClockWidget"
  options:
    label: "{%H:%M}"
"""
        parsed, _ = parse_yaml(yaml_text)
        result, error = extract_widget_options(parsed)
        assert error is None
        assert result["label"] == "{%H:%M}"

    def test_extract_plain_options(self):
        """If it's already just options, return it as-is."""
        yaml_text = """
label: "{%H:%M}"
timezones: []
"""
        parsed, _ = parse_yaml(yaml_text)
        result, error = extract_widget_options(parsed)
        assert error is None
        assert result["label"] == "{%H:%M}"

    def test_extract_empty_options(self):
        """Empty options is fine, just return empty dict."""
        yaml_text = """
type: "yasb.clock.ClockWidget"
options: {}
"""
        parsed, _ = parse_yaml(yaml_text)
        result, error = extract_widget_options(parsed)
        assert error is None
        assert result == {}

    def test_extract_from_invalid_yaml(self):
        """Can't extract from broken YAML."""
        yaml_text = "invalid: yaml:\n  bad"
        parsed, parse_error = parse_yaml(yaml_text)
        if parsed is None:
            assert parse_error is not None
        else:
            result, error = extract_widget_options(parsed)
            assert result is None or error is not None


class TestEdgeCases:
    """Weird inputs and special characters."""

    def test_yaml_with_special_characters(self):
        """Handle escaped unicode and HTML entities."""
        yaml_text = """
label: "<span>\\ue001</span>"
format: "{%H:%M:%S}"
"""
        result, error = parse_yaml(yaml_text)
        assert error is None
        assert "<span>" in result["label"]

    def test_yaml_with_unicode(self):
        """Unicode emoji and text should work."""
        yaml_text = """
icon: "🕐"
label: "时钟"
"""
        result, error = parse_yaml(yaml_text)
        assert error is None
        assert result["icon"] == "🕐"
        assert result["label"] == "时钟"

    def test_yaml_with_multiline_string(self):
        """Multiline strings with | should work."""
        yaml_text = """
description: |
  This is a
  multiline string
"""
        result, error = parse_yaml(yaml_text)
        assert error is None
        assert "multiline" in result["description"]

    def test_yaml_preserves_quotes(self):
        """Don't mess with quoted values when formatting."""
        yaml_text = 'label: "{%H:%M}"'
        result, error = format_yaml(yaml_text)
        assert error is None
        parsed, _ = parse_yaml(result)
        assert parsed["label"] == "{%H:%M}"
