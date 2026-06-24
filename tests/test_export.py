from __future__ import annotations

from portfolio_management.tabs import export


def test_import_market_data_logs_missing_paths(monkeypatch: object) -> None:
    logged: list[tuple[str, str]] = []

    def capture_error(*, pipeline_name: str, error_message: str) -> None:
        logged.append((pipeline_name, error_message))

    monkeypatch.setattr(export, "log_import_error", capture_error)

    prices_path, fx_path, status = export._import_market_data("", "")

    assert prices_path == ""
    assert fx_path == ""
    assert status == "Both the market prices and FX rates Delta table paths are required."
    assert logged == [("delta_market_data", status)]
