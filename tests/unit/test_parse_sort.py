"""Unit tests for `clickup.cli.task_filters.parse_sort`.

The integration tests in `tests/integration/test_task_commands.py` exercise
the full Typer pipeline. These unit tests pin the parser's contract
directly so edge cases are cheap to add and fast to run.
"""

import pytest
import typer

from clickup.cli.shared import resolve_list_ids, split_csv
from clickup.cli.task_filters import (
    annotate_source_list,
    epoch_ms,
    parse_sort,
    set_exclusive_date_filter,
)
from clickup.core import Config


class TestParseSortAcceptedForms:
    def test_none_passes_through_reverse(self):
        assert parse_sort(None, reverse_flag=False) == (None, False)
        assert parse_sort(None, reverse_flag=True) == (None, True)

    def test_plain_field_no_reverse(self):
        assert parse_sort("updated", reverse_flag=False) == ("updated", False)

    def test_plain_field_with_reverse(self):
        assert parse_sort("updated", reverse_flag=True) == ("updated", True)

    def test_colon_desc(self):
        assert parse_sort("updated:desc", reverse_flag=False) == ("updated", True)

    def test_colon_asc(self):
        assert parse_sort("updated:asc", reverse_flag=False) == ("updated", False)

    def test_minus_prefix_is_desc(self):
        assert parse_sort("-updated", reverse_flag=False) == ("updated", True)

    def test_plus_prefix_is_asc(self):
        assert parse_sort("+updated", reverse_flag=False) == ("updated", False)

    def test_direction_is_case_insensitive(self):
        assert parse_sort("updated:DESC", reverse_flag=False) == ("updated", True)
        assert parse_sort("updated:Asc", reverse_flag=False) == ("updated", False)

    def test_whitespace_is_stripped(self):
        assert parse_sort("  updated  ", reverse_flag=False) == ("updated", False)
        assert parse_sort("  updated  :  desc  ", reverse_flag=False) == ("updated", True)
        assert parse_sort("-  updated  ", reverse_flag=False) == ("updated", True)


class TestParseSortUsageErrors:
    @pytest.mark.parametrize("bad", ["", "   ", "\t"])
    def test_empty_or_whitespace_only_input(self, bad):
        with pytest.raises(typer.Exit) as exc:
            parse_sort(bad, reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_lone_minus_is_empty_field(self):
        with pytest.raises(typer.Exit) as exc:
            parse_sort("-", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_lone_plus_is_empty_field(self):
        with pytest.raises(typer.Exit) as exc:
            parse_sort("+", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_colon_with_empty_field(self):
        with pytest.raises(typer.Exit) as exc:
            parse_sort(":desc", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_colon_with_empty_direction(self):
        with pytest.raises(typer.Exit) as exc:
            parse_sort("updated:", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_invalid_direction(self):
        with pytest.raises(typer.Exit) as exc:
            parse_sort("updated:sideways", reverse_flag=False)
        assert exc.value.exit_code == 2

    def test_colon_desc_with_reverse_flag_conflicts(self):
        with pytest.raises(typer.Exit) as exc:
            parse_sort("updated:desc", reverse_flag=True)
        assert exc.value.exit_code == 2

    def test_minus_prefix_with_reverse_flag_conflicts(self):
        with pytest.raises(typer.Exit) as exc:
            parse_sort("-updated", reverse_flag=True)
        assert exc.value.exit_code == 2

    def test_plus_prefix_with_reverse_flag_conflicts(self):
        with pytest.raises(typer.Exit) as exc:
            parse_sort("+updated", reverse_flag=True)
        assert exc.value.exit_code == 2


class TestAgentListHelpers:
    def test_split_csv_trims_values(self):
        assert split_csv(" a, b ,c ") == ["a", "b", "c"]
        assert split_csv(None) == []

    def test_split_csv_rejects_empty_parts(self):
        with pytest.raises(typer.Exit) as exc:
            split_csv("a,,b")
        assert exc.value.exit_code == 2

    def test_resolve_list_ids_uses_default_and_aliases(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        config = Config()
        config.set("default_list_id", "default-list")
        config.set("default_lists", {"work": "listA", "home": "listB"})

        assert resolve_list_ids(None) == ["default-list"]
        assert resolve_list_ids("work,home") == ["listA", "listB"]
        assert resolve_list_ids(None, all_lists=True) == ["listA", "listB"]

    def test_resolve_list_ids_all_lists_requires_aliases(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLICKUP_CONFIG_PATH", str(tmp_path / "config.json"))
        with pytest.raises(typer.Exit) as exc:
            resolve_list_ids(None, all_lists=True)
        assert exc.value.exit_code == 2

    def test_epoch_ms_accepts_supported_date_forms(self):
        assert epoch_ms("1777593600000") == 1777593600000
        assert epoch_ms("2026-05-01") == 1777593600000
        assert epoch_ms("2026-05-01T03:00:00Z") == 1777604400000
        assert epoch_ms("2026-05-01T03:00:00") == 1777604400000

    def test_epoch_ms_accepts_relative_duration(self):
        before = epoch_ms("1d")
        now_ms = epoch_ms("0d")
        assert 23 * 60 * 60 * 1000 <= now_ms - before <= 25 * 60 * 60 * 1000

    @pytest.mark.parametrize("bad", ["", "not-a-date"])
    def test_epoch_ms_rejects_invalid_values(self, bad):
        with pytest.raises(typer.Exit) as exc:
            epoch_ms(bad)
        assert exc.value.exit_code == 2

    def test_set_exclusive_date_filter_sets_single_value(self):
        filters = {}
        set_exclusive_date_filter(filters, "date_created_gt", [("--created-after", "2026-05-01")])
        assert filters == {"date_created_gt": 1777593600000}

    def test_set_exclusive_date_filter_rejects_conflicts(self):
        with pytest.raises(typer.Exit) as exc:
            set_exclusive_date_filter(
                {},
                "date_created_gt",
                [("--created-since", "7d"), ("--created-after", "2026-05-01")],
            )
        assert exc.value.exit_code == 2

    def test_annotate_source_list_tolerates_non_extensible_objects(self):
        class Locked:
            __slots__ = ()

        locked = Locked()
        assert annotate_source_list(locked, "listA") is locked
