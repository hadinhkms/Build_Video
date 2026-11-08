"""
Client Vbee TTS (https://vbee.vn) — dịch vụ trả phí, cần VBEE_APP_ID + VBEE_ACCESS_TOKEN trong .env.

API bất đồng bộ: POST /tts nhận request_id -> GET /tts/{request_id} tới khi có audio_link -> tải mp3.
Chuyển thể từ auto-video-gen/src/tts/vbee-client.ts. Vbee không trả mốc thời gian từng từ.
"""
import os
import time

import requests

DEFAULT_ENDPOINT = "https://vbee.vn/api/v1"
DEFAULT_VOICE_CODE = "n_hanoi_male_protrainer_education_vc"
# API bắt buộc có callback_url dù ta dùng polling, nên truyền URL giả
DUMMY_CALLBACK_URL = "https://example.com/callback"
SUBMIT_RETRY_DELAYS_SEC = (1, 2, 4)


class VbeeError(Exception):
    """Lỗi từ Vbee (sai token, hết ký tự, xử lý thất bại, quá thời gian chờ...)."""


class VbeeClient:
    def __init__(self, app_id: str, access_token: str, voice_code: str = DEFAULT_VOICE_CODE,
                 speed_rate: float = 1.0, endpoint: str = DEFAULT_ENDPOINT,
                 poll_interval_sec: float = 2.0, poll_timeout_sec: float = 60.0, session=None):
        self.app_id = app_id
        self.access_token = access_token
        self.voice_code = voice_code
        self.speed_rate = speed_rate
        self.endpoint = endpoint.rstrip("/")
        self.poll_interval_sec = poll_interval_sec
        self.poll_timeout_sec = poll_timeout_sec
        self.session = session or requests.Session()

    @classmethod
    def from_settings(cls, cfg: dict) -> "VbeeClient":
        """Khóa bí mật đọc từ biến môi trường / file .env; giọng và tốc độ đọc từ settings.audio.vbee."""
        from dotenv import load_dotenv
        load_dotenv()
        app_id = os.environ.get("VBEE_APP_ID", "").strip()
        access_token = os.environ.get("VBEE_ACCESS_TOKEN", "").strip()
        if not app_id or not access_token:
            raise VbeeError(
                "Chọn TTS Vbee nhưng thiếu VBEE_APP_ID / VBEE_ACCESS_TOKEN. "
                "Chép .env.example thành .env ở thư mục gốc rồi điền khóa, hoặc dùng --tts edge."
            )
        return cls(
            app_id, access_token,
            voice_code=cfg.get("voice_code", DEFAULT_VOICE_CODE),
            speed_rate=cfg.get("speed_rate", 1.0),
            poll_timeout_sec=cfg.get("poll_timeout_sec", 60.0),
        )

    def synthesize(self, text: str, output_path: str, voice_code: str = None) -> None:
        """Sinh giọng đọc cho `text` và lưu mp3 vào `output_path`."""
        created = self._submit(text, voice_code or self.voice_code)
        audio_link = created.get("audio_link") or self._poll(created["request_id"])
        resp = self.session.get(audio_link, timeout=60)  # link CDN tạm thời, không cần token
        resp.raise_for_status()
        if not resp.content:
            raise VbeeError(f"File audio Vbee rỗng: {audio_link}")
        with open(output_path, "wb") as f:
            f.write(resp.content)

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"}

    def _submit(self, text: str, voice_code: str) -> dict:
        """Chỉ thử lại khi lỗi mạng hoặc HTTP 5xx; lỗi nghiệp vụ (status=0) báo ngay."""
        body = {
            "app_id": self.app_id,
            "input_text": text,
            "voice_code": voice_code,
            "audio_type": "mp3",
            "speed_rate": self.speed_rate,
            "callback_url": DUMMY_CALLBACK_URL,
        }
        for delay in (*SUBMIT_RETRY_DELAYS_SEC, None):
            try:
                resp = self.session.post(f"{self.endpoint}/tts", json=body, headers=self._headers(), timeout=30)
                if resp.status_code < 500:
                    return self._result(resp)
                error = f"HTTP {resp.status_code}"
            except requests.RequestException as e:
                error = str(e)
            if delay is None:
                raise VbeeError(f"Không gửi được yêu cầu tới Vbee sau nhiều lần thử: {error}")
            time.sleep(delay)

    def _poll(self, request_id: str) -> str:
        deadline = time.monotonic() + self.poll_timeout_sec
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval_sec)
            try:
                resp = self.session.get(f"{self.endpoint}/tts/{request_id}", headers=self._headers(), timeout=30)
            except requests.RequestException:
                continue  # lỗi mạng thoáng qua, thử lại ở vòng sau
            if resp.status_code >= 500:
                continue
            result = self._result(resp)
            if result.get("status") == "SUCCESS" and result.get("audio_link"):
                return result["audio_link"]
            if result.get("status") == "FAILURE":
                raise VbeeError(f"Vbee xử lý thất bại (request_id={request_id})")
        raise VbeeError(f"Quá {self.poll_timeout_sec:g}s chờ Vbee trả audio (request_id={request_id})")

    @staticmethod
    def _result(resp) -> dict:
        """Bóc `result` từ phản hồi {status: 1, result} hoặc báo lỗi {status: 0, error_code, error_message}."""
        try:
            data = resp.json()
        except ValueError:
            raise VbeeError(f"Vbee trả về HTTP {resp.status_code} không phải JSON")
        if data.get("status") != 1:
            detail = data.get("error_message") or data.get("error_code") or f"HTTP {resp.status_code}"
            raise VbeeError(f"Vbee báo lỗi: {detail}")
        return data["result"]
