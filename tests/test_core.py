import os

from microvault import core


def _fast_kdf(monkeypatch):
    # Keep the tests quick while exercising the same store format and APIs.
    monkeypatch.setattr(core, "PBKDF2_ITERATIONS", 1_000)


def test_encrypted_store_round_trip_and_backup(monkeypatch, tmp_path):
    _fast_kdf(monkeypatch)
    path = tmp_path / "external" / "store.enc"

    data, salt, key = core.load_store(str(path), "correct horse")
    assert data == {}
    core.save_store(str(path), data, salt, key)

    loaded, loaded_salt, loaded_key = core.load_store(str(path), "correct horse")
    assert loaded == {}
    assert loaded_salt == salt
    assert loaded_key == key
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert not (tmp_path / "external" / "store.enc.tmp").exists()

    core.snapshot_backup(str(path))
    backup = tmp_path / "external" / "backups" / "store-backup.enc"
    assert backup.read_bytes() == path.read_bytes()
    assert os.stat(backup).st_mode & 0o777 == 0o600


def test_encrypted_store_rejects_wrong_password_and_corruption(monkeypatch, tmp_path):
    _fast_kdf(monkeypatch)
    path = tmp_path / "store.enc"
    data, salt, key = core.load_store(str(path), "right")
    core.save_store(str(path), data, salt, key)

    assert core.load_store(str(path), "wrong") == (None, None, None)

    path.write_bytes(b"short")
    assert core.load_store(str(path), "right") == (None, None, None)


def test_parse_key_file_supports_common_shell_formats(tmp_path):
    path = tmp_path / "keys.txt"
    path.write_text(
        "\n".join(
            [
                "# comment",
                "openai=sk-test",
                "export github: ghp_test",
                "wpscan_api WPSCAN_TEST",
                "malformed",
            ]
        ),
        encoding="utf-8",
    )

    entries, failed_lines = core.parse_key_file(str(path))

    assert entries == {
        "openai": "sk-test",
        "github": "ghp_test",
        "wpscan_api": "WPSCAN_TEST",
    }
    assert failed_lines == [5]
