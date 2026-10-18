from pathlib import Path

import pytest

from accounting_agent import api, config, services, storage


@pytest.fixture
def app_dirs(tmp_path, monkeypatch):
    """Dane aplikacji i foldery dokumentów w katalogu tymczasowym."""
    data = tmp_path / "dane"
    monkeypatch.setattr(config, "app_data_dir", lambda: data)
    monkeypatch.setattr(storage, "app_data_dir", lambda: data)
    monkeypatch.setattr(services, "app_data_dir", lambda: data)
    cert = tmp_path / "cert.crt"
    cert.write_text("")
    cfg = config.Config(
        ksef_env="test",
        nip="5265877635",
        cert_path=cert,
        key_path=cert,
        output_dir=tmp_path / "Faktury ZAKUPOWE",
        statements_dir=tmp_path / "Wyciągi",
    )
    monkeypatch.setattr(api, "load_config", lambda: cfg)
    return cfg


@pytest.fixture
def statements_folder(app_dirs) -> Path:
    return app_dirs.statements_dir / "Sierpień 2026"
