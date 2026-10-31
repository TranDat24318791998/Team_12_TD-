"""
Client Python cho Muse API Gateway (v0.1.0) — https://muse-api.butterflyro.space

Luồng sử dụng (theo OpenAPI spec):
  1. POST /v1/videos            -> xếp hàng tác vụ, trả về task_id (HTTP 202)
  2. GET  /v1/videos/{task_id}  -> poll cho tới khi completed / failed
  3. GET  /v1/media/{name}      -> tải file kết quả (cùng Bearer token)

Xác thực: header "Authorization: Bearer <ClientKey>".

Cài đặt:
    pip install requests

Dùng từ dòng lệnh:
    export MUSE_API_KEY="your-client-key"
    python muse_client.py "A corgi surfing at sunset" --duration 8 --aspect-ratio 16:9
    python muse_client.py "Make the cat blink" --image cat.jpg          # image-to-video

Dùng trong code:
    from muse_client import MuseClient
    client = MuseClient()                     # đọc MUSE_API_KEY
    task, files = client.generate_video("A corgi surfing at sunset", duration=8)

Lưu ý: spec không mô tả cấu trúc JSON trả về (response schema rỗng), nên phần đọc
task_id / status / URL media dò theo nhiều tên trường phổ biến. Khi đã biết chính xác
cấu trúc, bạn có thể rút gọn các hàm _first / task_status / find_media_urls.
"""

from __future__ import annotations

import argparse
import base64
import mimetypes

from dotenv import load_dotenv
import os

load_dotenv()
# import os
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse

import requests

DEFAULT_BASE_URL = "https://muse-api.butterflyro.space"

_SUCCESS_STATES = {"completed", "complete", "succeeded", "success", "done", "finished"}
_FAILURE_STATES = {"failed", "failure", "error", "errored", "cancelled", "canceled", "expired", "timeout"}
_MEDIA_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".gif", ".png", ".jpg", ".jpeg", ".webp")
# Các trường có thể là dữ liệu đầu vào được gateway trả lại -> bỏ qua khi dò URL kết quả
_ECHO_KEYS = {"image", "images", "image_url", "reference_image", "request", "input", "params", "prompt"}


# --------------------------------------------------------------------------- lỗi

class MuseError(Exception):
    """Lỗi chung của client."""


class MuseAPIError(MuseError):
    """Gateway trả về mã HTTP lỗi (401, 404, 422, 5xx...)."""

    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(f"[HTTP {status_code}] {message}")
        self.status_code = status_code
        self.body = body


class MuseTaskFailed(MuseError):
    """Tác vụ video kết thúc với trạng thái thất bại."""

    def __init__(self, task: dict):
        self.task = task
        reason = _first(task, "error", "failure_reason", "reason", "message", "detail")
        super().__init__(f"Task {_extract_task_id(task) or '?'} thất bại: {reason or task}")


# --------------------------------------------------------------------------- client

class MuseClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        request_timeout: float = 60.0,
        session: requests.Session | None = None,
    ):
        self.api_key = api_key or os.environ.get("MUSE_API_KEY")
        if not self.api_key:
            raise ValueError("Thiếu API key: truyền api_key=... hoặc đặt biến môi trường MUSE_API_KEY")
        self.base_url = (base_url or os.environ.get("MUSE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.request_timeout = request_timeout
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "muse-client-python/0.1")

    # ---- nội bộ -------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _request(self, method: str, path: str, *, auth: bool = True,
                 headers: dict[str, str] | None = None, **kwargs: Any) -> requests.Response:
        hdrs = {"Accept": "application/json", **(headers or {})}
        if auth:
            hdrs.update(self._auth_headers())
        kwargs.setdefault("timeout", self.request_timeout)
        resp = self.session.request(method, self.base_url + path, headers=hdrs, **kwargs)
        if resp.status_code >= 400:
            raise _to_error(resp)
        return resp

    # ---- endpoint -----------------------------------------------------------

    def health(self) -> Any:
        """GET /healthz — chỉ cho biết gateway đang chạy, không kiểm tra phiên Muse."""
        return _json_or_text(self._request("GET", "/healthz", auth=False))

    def create_video(
        self,
        prompt: str,
        *,
        model: str = "muse-video",
        duration: int | None = None,         # 1–120 giây (Muse quyết định độ dài thực tế)
        size: str | None = None,
        aspect_ratio: str | None = None,     # vd "16:9", "9:16"
        resolution: str | None = None,       # vd "720p", "1080p"
        timeout: int | None = None,          # 1–1800 giây, thời gian gateway chờ sinh video
        extra: str | None = None,
        image: Any = None,
        images: list[Any] | None = None,
        image_url: Any = None,
        reference_image: str | None = None,
        idempotency_key: str | None = None,  # gửi lại cùng key để tránh tạo trùng task
    ) -> dict:
        """POST /v1/videos — xếp hàng tác vụ text-to-video hoặc image-to-video."""
        if not 1 <= len(prompt) <= 32000:
            raise ValueError("prompt phải dài 1–32000 ký tự")
        if duration is not None and not 1 <= duration <= 120:
            raise ValueError("duration phải trong khoảng 1–120 giây")
        if timeout is not None and not 1 <= timeout <= 1800:
            raise ValueError("timeout phải trong khoảng 1–1800 giây")

        body = {
            "prompt": prompt, "model": model, "duration": duration, "size": size,
            "aspect_ratio": aspect_ratio, "resolution": resolution, "timeout": timeout,
            "extra": extra, "image": image, "images": images, "image_url": image_url,
            "reference_image": reference_image,
        }
        body = {k: v for k, v in body.items() if v is not None}
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request("POST", "/v1/videos", json=body, headers=headers).json()

    def get_video(self, task_id: str) -> dict:
        """GET /v1/videos/{task_id} — tiến độ, lỗi, và URL media khi hoàn tất."""
        return self._request("GET", f"/v1/videos/{quote(task_id, safe='')}").json()

    def wait_for_video(
        self,
        task_id: str,
        *,
        poll_interval: float = 5.0,
        max_wait: float = 1900.0,
        on_update: Callable[[dict], None] | None = None,
    ) -> dict:
        """Poll tới khi task hoàn tất. Ném MuseTaskFailed nếu thất bại, TimeoutError nếu quá max_wait."""
        deadline = time.monotonic() + max_wait
        while True:
            task: dict | None = None
            try:
                task = self.get_video(task_id)
            except MuseAPIError as e:
                if e.status_code < 500 and e.status_code != 429:
                    raise                       # lỗi phía client (401, 404...) -> dừng ngay
            except requests.RequestException:
                pass                            # lỗi mạng tạm thời -> thử lại

            if task is not None:
                if on_update:
                    on_update(task)
                status = task_status(task)
                if status in _SUCCESS_STATES:
                    return task
                if status in _FAILURE_STATES:
                    raise MuseTaskFailed(task)
                if status is None and find_media_urls(task):
                    return task

            if time.monotonic() + poll_interval > deadline:
                raise TimeoutError(f"Quá {max_wait:.0f}s mà task {task_id} vẫn chưa xong")
            time.sleep(poll_interval)

    def media_url(self, name_or_url: str) -> str:
        if name_or_url.startswith(("http://", "https://")):
            return name_or_url
        if name_or_url.startswith("/"):
            return self.base_url + name_or_url
        return f"{self.base_url}/v1/media/{quote(name_or_url, safe='')}"

    def download_media(self, name_or_url: str, dest_dir: str | os.PathLike = "outputs",
                       filename: str | None = None) -> Path:
        """GET /v1/media/{name} — nhận tên file hoặc URL lấy từ task, lưu xuống đĩa."""
        url = self.media_url(name_or_url)
        same_host = urlparse(url).netloc == urlparse(self.base_url).netloc
        headers = {"Accept": "*/*", **(self._auth_headers() if same_host else {})}  # không gửi token ra host lạ

        with self.session.get(url, headers=headers, stream=True, timeout=self.request_timeout) as resp:
            if resp.status_code >= 400:
                raise _to_error(resp)
            dest = Path(dest_dir)
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / (filename or _filename_for(url, resp.headers.get("Content-Type")))
            tmp = path.with_name(path.name + ".part")
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
            tmp.replace(path)
        return path

    def generate_video(
        self,
        prompt: str,
        *,
        dest_dir: str | os.PathLike = "outputs",
        poll_interval: float = 5.0,
        max_wait: float | None = None,
        on_update: Callable[[dict], None] | None = None,
        **params: Any,
    ) -> tuple[dict, list[Path]]:
        """Trọn gói: tạo task -> chờ -> tải toàn bộ file kết quả. Trả về (task cuối, danh sách file)."""
        created = self.create_video(prompt, **params)
        if on_update:
            on_update(created)
        task_id = _extract_task_id(created)
        if not task_id:
            raise MuseError(f"Không tìm thấy task_id trong phản hồi: {created}")

        if max_wait is None:
            max_wait = (params.get("timeout") or 1800) + 120
        task = self.wait_for_video(task_id, poll_interval=poll_interval,
                                   max_wait=max_wait, on_update=on_update)
        urls = find_media_urls(task)
        if not urls:
            raise MuseError(f"Task đã xong nhưng không thấy URL media: {task}")
        return task, [self.download_media(u, dest_dir) for u in urls]


# --------------------------------------------------------------------------- tiện ích

def _first(obj: Any, *keys: str) -> Any:
    """Giá trị đầu tiên khác None trong các key; tìm cả trong obj['data'|'task'|'result']."""
    if not isinstance(obj, dict):
        return None
    scopes = [obj] + [obj[k] for k in ("data", "task", "result") if isinstance(obj.get(k), dict)]
    for scope in scopes:
        for key in keys:
            if scope.get(key) is not None:
                return scope[key]
    return None


def _extract_task_id(obj: Any) -> str | None:
    value = _first(obj, "task_id", "id")
    return str(value) if value is not None else None


def task_status(task: Any) -> str | None:
    value = _first(task, "status", "state")
    return str(value).lower() if value is not None else None


def find_media_urls(task: Any) -> list[str]:
    """Dò URL kết quả trong JSON task. Ưu tiên URL /v1/media/ của gateway."""
    gateway, other, bare = [], [], []

    def walk(node: Any, key: str | None = None) -> None:
        if key in _ECHO_KEYS:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str):
            if "/v1/media/" in node:
                gateway.append(node)
            elif node.startswith(("http://", "https://")):
                if urlparse(node).path.lower().endswith(_MEDIA_EXTS):
                    other.append(node)
            elif "/" not in node and node.lower().endswith(_MEDIA_EXTS):
                bare.append(node)

    walk(task)
    return list(dict.fromkeys(gateway or other or bare))


def file_to_data_url(path: str | os.PathLike) -> str:
    """Đọc ảnh local thành data URL (base64) để gửi kèm image-to-video."""
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def _json_or_text(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


def _to_error(resp: requests.Response) -> MuseAPIError:
    body = _json_or_text(resp)
    message = resp.reason or "HTTP error"
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body.get("message")
        if isinstance(detail, list):  # 422 HTTPValidationError
            message = "; ".join(
                f"{'.'.join(map(str, d.get('loc', [])))}: {d.get('msg')}" for d in detail if isinstance(d, dict)
            )
        elif isinstance(detail, dict):
            message = str(detail.get("message") or detail)
        elif detail:
            message = str(detail)
    elif isinstance(body, str) and body.strip():
        message = body.strip()[:500]
    return MuseAPIError(resp.status_code, message, body)


def _filename_for(url: str, content_type: str | None) -> str:
    name = unquote(Path(urlparse(url).path).name) or f"muse-{int(time.time())}"
    if not Path(name).suffix and content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            name += ext
    return name


# --------------------------------------------------------------------------- CLI

def _make_printer() -> Callable[[dict], None]:
    last: list[str] = []

    def show(task: dict) -> None:
        status = task_status(task) or "?"
        progress = _first(task, "progress", "percent")
        line = f"task {_extract_task_id(task) or '?'}: {status}" + (f" ({progress})" if progress is not None else "")
        if not last or last[-1] != line:
            print(line, flush=True)
            last.append(line)

    return show


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Tạo video bằng Muse API Gateway")
    p.add_argument("prompt", help="Mô tả video")
    p.add_argument("--model", default="muse-video")
    p.add_argument("--duration", type=int, help="1–120 giây")
    p.add_argument("--aspect-ratio", help='vd "16:9"')
    p.add_argument("--resolution", help='vd "720p"')
    p.add_argument("--size")
    p.add_argument("--image", help="URL ảnh hoặc đường dẫn ảnh local (image-to-video)")
    p.add_argument("--timeout", type=int, help="Thời gian tối đa gateway chờ sinh video (1–1800s)")
    p.add_argument("--idempotency-key")
    p.add_argument("--out", default="outputs", help="Thư mục lưu file (mặc định: outputs)")
    p.add_argument("--poll", type=float, default=5.0, help="Chu kỳ poll, giây")
    p.add_argument("--base-url", default=None)
    args = p.parse_args(argv)

    params: dict[str, Any] = {
        "model": args.model, "duration": args.duration, "aspect_ratio": args.aspect_ratio,
        "resolution": args.resolution, "size": args.size, "timeout": args.timeout,
        "idempotency_key": args.idempotency_key,
    }
    if args.image:
        if args.image.startswith(("http://", "https://", "data:")):
            params["image_url"] = args.image
        else:
            params["image"] = file_to_data_url(args.image)

    try:
        client = MuseClient(base_url=args.base_url)
        _, files = client.generate_video(args.prompt, dest_dir=args.out, poll_interval=args.poll,
                                         on_update=_make_printer(), **params)
    except (MuseError, TimeoutError, ValueError, requests.RequestException) as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 1

    for f in files:
        print(f"Đã lưu: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
