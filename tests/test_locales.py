"""
Tests for locale files - keeping translations in sync.

When someone adds a new translation (e.g., de.json, pt_BR.json), we need to make sure:
- They didn't forget any keys from en.json
- They didn't add extra keys that don't exist in en.json
- Keys are in the same order as en.json (makes diffs cleaner)
- All values are actual strings, not empty or null

en.json is the source of truth. All other locales must match its structure exactly.
"""

import json
from pathlib import Path

import pytest

LOCALES_DIR = Path(__file__).parent.parent / "app" / "core" / "locales"
REFERENCE_LOCALE = "en.json"


def get_locale_files():
    """Find all .json files in the locales directory."""
    if not LOCALES_DIR.exists():
        pytest.skip(f"Locales directory not found: {LOCALES_DIR}")

    locale_files = list(LOCALES_DIR.glob("*.json"))
    if not locale_files:
        pytest.skip(f"No locale files found in {LOCALES_DIR}")

    return locale_files


def load_json_preserve_order(file_path):
    """Load JSON while keeping keys in their original order."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        data = json.loads(content)
    return data


def get_keys_in_order(data):
    """Extract all keys from a dict, maintaining order."""
    return list(data.keys())


class TestLocaleConsistency:
    """Make sure all locale files have the same structure."""

    @pytest.fixture
    def reference_locale(self):
        """Load en.json as our reference."""
        ref_path = LOCALES_DIR / REFERENCE_LOCALE
        if not ref_path.exists():
            pytest.skip(f"Reference locale not found: {ref_path}")
        return load_json_preserve_order(ref_path)

    @pytest.fixture
    def reference_keys(self, reference_locale):
        """Extract the keys from en.json in order."""
        return get_keys_in_order(reference_locale)

    def test_reference_locale_exists(self):
        """Check that en.json actually exists."""
        ref_path = LOCALES_DIR / REFERENCE_LOCALE
        assert ref_path.exists(), f"Reference locale file not found: {ref_path}"

    def test_reference_locale_is_valid_json(self, reference_locale):
        """Make sure en.json is valid JSON and not empty."""
        assert isinstance(reference_locale, dict), "Reference locale must be a dictionary"
        assert len(reference_locale) > 0, "Reference locale must not be empty"

    def test_reference_locale_has_metadata(self, reference_locale):
        """en.json needs _language_name and _language_code fields."""
        required_metadata = ["_language_name", "_language_code"]
        for key in required_metadata:
            assert key in reference_locale, f"Reference locale missing required metadata: {key}"

    @pytest.mark.parametrize("locale_file", get_locale_files())
    def test_locale_is_valid_json(self, locale_file):
        """Each locale file should be valid JSON."""
        data = load_json_preserve_order(locale_file)
        assert isinstance(data, dict), f"{locale_file.name} must contain a JSON object"
        assert len(data) > 0, f"{locale_file.name} must not be empty"

    @pytest.mark.parametrize("locale_file", get_locale_files())
    def test_locale_has_all_keys(self, locale_file, reference_keys):
        """Make sure no translation keys are missing."""
        if locale_file.name == REFERENCE_LOCALE:
            return

        locale_data = load_json_preserve_order(locale_file)
        locale_keys = get_keys_in_order(locale_data)

        missing_keys = set(reference_keys) - set(locale_keys)

        assert not missing_keys, f"{locale_file.name} is missing the following keys:\n" + "\n".join(
            f"  - {key}" for key in sorted(missing_keys)
        )

    @pytest.mark.parametrize("locale_file", get_locale_files())
    def test_locale_has_no_extra_keys(self, locale_file, reference_keys):
        """Check for keys that shouldn't be there."""
        if locale_file.name == REFERENCE_LOCALE:
            return

        locale_data = load_json_preserve_order(locale_file)
        locale_keys = get_keys_in_order(locale_data)

        extra_keys = set(locale_keys) - set(reference_keys)

        assert not extra_keys, f"{locale_file.name} has the following extra keys:\n" + "\n".join(
            f"  - {key}" for key in sorted(extra_keys)
        )

    @pytest.mark.parametrize("locale_file", get_locale_files())
    def test_locale_key_order_matches_reference(self, locale_file, reference_keys):
        """Keys should be in the same order as en.json (makes git diffs cleaner)."""
        if locale_file.name == REFERENCE_LOCALE:
            return

        locale_data = load_json_preserve_order(locale_file)
        locale_keys = get_keys_in_order(locale_data)

        # Only check order if keys match (other tests handle missing/extra keys)
        if set(locale_keys) != set(reference_keys):
            pytest.skip(f"{locale_file.name} has different keys (tested separately)")

        mismatched_positions = []
        for i, (ref_key, loc_key) in enumerate(zip(reference_keys, locale_keys)):
            if ref_key != loc_key:
                mismatched_positions.append({"position": i + 1, "expected": ref_key, "actual": loc_key})

        if mismatched_positions:
            error_msg = f"{locale_file.name} has different key order:\n"
            for mismatch in mismatched_positions[:10]:
                error_msg += (
                    f"  Position {mismatch['position']}: "
                    f"expected '{mismatch['expected']}', "
                    f"got '{mismatch['actual']}'\n"
                )
            if len(mismatched_positions) > 10:
                error_msg += f"  ... and {len(mismatched_positions) - 10} more mismatches\n"

            assert False, error_msg

    @pytest.mark.parametrize("locale_file", get_locale_files())
    def test_locale_has_metadata(self, locale_file):
        """Every locale needs _language_name and _language_code."""
        locale_data = load_json_preserve_order(locale_file)

        required_metadata = ["_language_name", "_language_code"]
        for key in required_metadata:
            assert key in locale_data, f"{locale_file.name} missing required metadata: {key}"
            assert locale_data[key], f"{locale_file.name} has empty value for {key}"

    @pytest.mark.parametrize("locale_file", get_locale_files())
    def test_locale_values_are_strings(self, locale_file):
        """All translation values must be non-empty strings."""
        locale_data = load_json_preserve_order(locale_file)

        invalid_values = []
        for key, value in locale_data.items():
            if not isinstance(value, str):
                invalid_values.append(f"{key}: {type(value).__name__} (expected string)")
            elif not value.strip():
                invalid_values.append(f"{key}: empty or whitespace-only string")

        assert not invalid_values, f"{locale_file.name} has invalid values:\n" + "\n".join(
            f"  - {val}" for val in invalid_values
        )

    @pytest.mark.parametrize("locale_file", get_locale_files())
    def test_locale_language_code_matches_filename(self, locale_file):
        """_language_code should match the filename (e.g., pt_BR.json -> pt_BR)."""
        if locale_file.name == REFERENCE_LOCALE:
            expected_code = "en"
        else:
            expected_code = locale_file.stem

        locale_data = load_json_preserve_order(locale_file)
        actual_code = locale_data.get("_language_code", "")

        assert actual_code == expected_code, (
            f"{locale_file.name} has language code '{actual_code}', but filename suggests '{expected_code}'"
        )


class TestLocaleCompleteness:
    """Overall checks to make sure translations are in good shape."""

    def test_all_locales_have_same_number_of_keys(self):
        """Every locale should have the exact same number of keys."""
        locale_files = get_locale_files()

        key_counts = {}
        for locale_file in locale_files:
            locale_data = load_json_preserve_order(locale_file)
            key_counts[locale_file.name] = len(locale_data)

        if not key_counts:
            pytest.skip("No locale files found")

        reference_count = key_counts.get(REFERENCE_LOCALE)
        if reference_count is None:
            pytest.skip(f"Reference locale {REFERENCE_LOCALE} not found")

        mismatches = []
        for filename, count in key_counts.items():
            if filename != REFERENCE_LOCALE and count != reference_count:
                mismatches.append(f"{filename}: {count} keys (expected {reference_count})")

        assert not mismatches, "The following locales have different number of keys:\n" + "\n".join(
            f"  - {mismatch}" for mismatch in mismatches
        )

    def test_locale_files_exist(self):
        """We should have at least one translation besides English."""
        locale_files = get_locale_files()
        non_reference_locales = [f for f in locale_files if f.name != REFERENCE_LOCALE]

        assert len(locale_files) > 0, "No locale files found"
        assert len(non_reference_locales) > 0, (
            f"Only reference locale ({REFERENCE_LOCALE}) exists. At least one translation should be present."
        )
