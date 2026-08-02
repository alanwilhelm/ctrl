from ctrl.redaction import redact_value


def test_redacts_secret_keys_and_credential_shaped_text() -> None:
    value = {
        "api_key": "should-not-appear",
        "message": "authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "nested": [{"password": "also-hidden"}],
    }

    redacted = redact_value(value)

    assert redacted["api_key"] == "[REDACTED]"
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted["message"]
    assert redacted["nested"][0]["password"] == "[REDACTED]"
