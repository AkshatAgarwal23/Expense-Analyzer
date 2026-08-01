from unittest.mock import MagicMock, patch

import pytest

from app.services import transcription_service
from app.services.transcription_service import TranscriptionError


def test_transcribe_calls_sarvam(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.transcription_service.settings.sarvam_api_key",
        "test-key",
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "request_id": "req-1",
        "transcript": "400 ka dinner Rahul ke saath split",
        "language_code": "hi-IN",
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("app.services.transcription_service.httpx.Client", return_value=mock_client):
        text = transcription_service.transcribe(b"fake-audio", "clip.webm")

    assert text == "400 ka dinner Rahul ke saath split"
    kwargs = mock_client.post.call_args.kwargs
    assert kwargs["headers"]["api-subscription-key"] == "test-key"
    assert kwargs["data"]["mode"] == "translit"


def test_transcribe_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.transcription_service.settings.sarvam_api_key",
        "",
    )
    with pytest.raises(TranscriptionError, match="SARVAM_API_KEY"):
        transcription_service.transcribe(b"fake", "a.wav")


def test_transcribe_surfaces_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.transcription_service.settings.sarvam_api_key",
        "test-key",
    )
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "forbidden"
    mock_response.json.return_value = {
        "error": {"message": "invalid api key", "code": "invalid_api_key_error"}
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("app.services.transcription_service.httpx.Client", return_value=mock_client):
        with pytest.raises(TranscriptionError, match="invalid api key"):
            transcription_service.transcribe(b"fake", "a.wav")
