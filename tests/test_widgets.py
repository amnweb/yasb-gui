"""
Tests for YAML indentation fixing with real widget configs.

When users copy widget options from docs or other configs, they often paste
it with broken indentation. The fix_yaml_indentation function should be able
to detect proper nesting from the widget schema and fix it automatically.

Fixtures in tests/fixtures/ represent real widget configs we need to handle.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
from core.code_editor import fix_yaml_indentation, validate_yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def flatten_yaml(yaml_text: str) -> str:
    """Strip all indentation to simulate a bad copy-paste job."""
    lines = yaml_text.split("\n")
    return "\n".join(line.strip() for line in lines)


def extract_widget_type(yaml_text: str) -> str | None:
    """Pull out the widget type from the first line: # Widget: yasb.xxx.XxxWidget"""
    match = re.search(r"#\s*Widget:\s*(\S+)", yaml_text)
    if match:
        return match.group(1)
    return None


def get_fixture_files() -> list[tuple[str, Path]]:
    """Find all widget_*.yaml test fixtures."""
    if not FIXTURES_DIR.exists():
        return []

    fixtures = []
    for yaml_file in sorted(FIXTURES_DIR.glob("widget_*.yaml")):
        name = yaml_file.stem.replace("widget_", "")
        fixtures.append((name, yaml_file))
    return fixtures


_fixtures = get_fixture_files() or [("_no_fixtures_", None)]
_fixture_ids = [name for name, _ in _fixtures]


@pytest.mark.parametrize("fixture_info", _fixtures, ids=_fixture_ids)
def test_fix_yaml_indentation(fixture_info: tuple[str, Path | None]):
    """
    Make sure we can fix badly indented widget configs.

    Takes a valid widget config, strips all indentation (simulating a bad paste),
    then tries to fix it using the widget schema.
    """
    name, fixture_path = fixture_info

    if fixture_path is None:
        pytest.skip("No fixtures found in tests/fixtures/")

    yaml_text = fixture_path.read_text(encoding="utf-8")
    widget_type = extract_widget_type(yaml_text)

    is_input_valid, input_errors = validate_yaml(yaml_text)
    assert is_input_valid, f"Fixture {name} has invalid YAML: {input_errors}"

    flattened = flatten_yaml(yaml_text)
    result, error = fix_yaml_indentation(flattened, widget_type)

    assert result is not None, "fix_yaml_indentation returned None"

    is_valid, errors = validate_yaml(result)
    assert is_valid, (
        f"Failed to fix YAML for {name} ({widget_type}):\n"
        f"Fix error: {error}\n"
        f"Validation errors: {[str(e) for e in errors]}\n"
        f"Flattened:\n{flattened[:500]}\n"
        f"Result:\n{result[:500]}"
    )


class TestEdgeCases:
    """Edge cases and weird inputs."""

    def test_already_valid_yaml(self):
        """Don't break YAML that's already properly indented."""
        valid_yaml = """label: "test"
chat:
  blur: true
  round_corners: true
callbacks:
  on_left: toggle_chat"""

        result, error = fix_yaml_indentation(valid_yaml, "yasb.ai_chat.AiChatWidget")

        assert error is None
        is_valid, _ = validate_yaml(result)
        assert is_valid

    def test_no_schema_available(self):
        """Should still work even if we don't have a schema for this widget."""
        yaml_text = """key1: value1
key2: value2"""

        result, error = fix_yaml_indentation(yaml_text, "unknown.widget.Type")

        is_valid, _ = validate_yaml(result)
        assert is_valid

    def test_tabs_converted_to_spaces(self):
        """Tabs should get converted to spaces."""
        yaml_with_tabs = "label: test\nchat:\n\tblur: true"

        result, _ = fix_yaml_indentation(yaml_with_tabs, "yasb.ai_chat.AiChatWidget")

        assert "\t" not in result

    def test_empty_input(self):
        """Empty in, empty out."""
        result, error = fix_yaml_indentation("", "yasb.clock.ClockWidget")
        assert result == ""
        assert error is None

    def test_whitespace_only(self):
        """Just whitespace should work fine."""
        result, error = fix_yaml_indentation("   \n  \n  ", "yasb.clock.ClockWidget")
        assert error is None
