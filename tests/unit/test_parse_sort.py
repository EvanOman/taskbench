"""Unit tests for `clickup.cli.commands.task._parse_sort`.

The integration tests in `tests/integration/test_task_commands.py` exercise
the full Typer pipeline. These unit tests pin the parser's contract
directly so edge cases are cheap to add and fast to run.
"""

import pytest
import typer

from clickup.cli.commands.task import _parse_sort


class TestParseSortAcceptedForms:
    def test_none_passes_through_reverse(self):
        assert _parse_sort(None, reverse_flag=False) == (None, False)
        assert _parse_sort(None, reverse_flag=True) == (None, True)

    def test_plain_field_no_reverse(self):
        assert _parse_sort("updated", reverse_flag=False) == ("updated", False)

    def test_plain_field_with_reverse(self):
        assert _parse_sort("updated", reverse_flag=True) == ("updated", True)

    def test_colon_desc(self):
        assert _parse_sort("updated:desc", reverse_flag=False) == ("updated", True)

    def test_colon_asc(self):
        assert _parse_sort("updated:asc", reverse_flag=False) == ("updated", False)

    def test_minus_prefix_is_desc(self):
        assert _parse_sort("-updated", reverse_flag=False) == ("updated", True)

    def test_plus_prefix_is_asc(self):
        assert _parse_sort("+updated", reverse_flag=False) == ("updated", False)

    def test_direction_is_case_insensitive(self):
        assert _parse_sort("updated:DESC", reverse_flag=False) == ("updated", True)
        assert _parse_sort("updated:Asc", reverse_flag=False) == ("updated", False)

    def test_whitespace_is_stripped(self):
        assert _parse_sort("  updated  ", reverse_flag=False) == ("updated", False)
        assert _parse_sort("  updated  :  desc  ", reverse_flag=False) == ("updated", True)
        assert _parse_sort("-  updated  ", reverse_flag=False) == ("updated", True)


class TestParseSortUsageErrors:
    @pytest.mark.parametrize("bad", ["", "   ", "\t"])
    def test_empty_or_whitespace_only_input(self, bad):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort(bad, reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_lone_minus_is_empty_field(self):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort("-", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_lone_plus_is_empty_field(self):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort("+", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_colon_with_empty_field(self):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort(":desc", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_colon_with_empty_direction(self):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort("updated:", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_invalid_direction(self):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort("updated:sideways", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_colon_desc_with_reverse_flag_conflicts(self):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort("updated:desc", reverse_flag=True)
        assert exc.value.exit_code == 2

    def test_minus_prefix_with_reverse_flag_conflicts(self):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort("-updated", reverse_flag=True)
        assert exc.value.exit_code == 2

    def test_plus_prefix_with_reverse_flag_conflicts(self):
        with pytest.raises(typer.Exit) as exc:
            _parse_sort("+updated", reverse_flag=True)
        assert exc.value.exit_code == 2
