"""
Docker-песочница для запуска кода, сгенерированного моделью (T3).

По заданию каждая попытка генерации кода запускается в изолированном
контейнере, чтобы вредоносный или просто кривой код от LLM не мог
повредить систему. Код передаётся в контейнер через stdin — никакие
папки хоста в контейнер не монтируются.

Ограничения контейнера:
    --network none            нет сети
    --read-only + tmpfs /tmp  файловая система только для чтения
    --user 65534:65534        непривилегированный пользователь nobody
    --cap-drop ALL            без Linux capabilities
    --security-opt no-new-privileges
    --memory / --cpus / --pids-limit   лимиты на память, CPU и fork-бомбы
    timeout                   зависший контейнер убивается
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass

DEFAULT_IMAGE = "python:3.12-slim"

# Явная кодировка: на Windows вывод docker может содержать кириллицу
# (например, путь C:\Users\Пользователь), а кодировка консоли — cp1251.
_TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}


@dataclass
class SandboxResult:
    ok: bool            # процесс завершился с кодом 0 и не по таймауту
    stdout: str
    stderr: str
    timed_out: bool = False


class DockerSandbox:
    """Запускает Python-скрипт в одноразовом изолированном контейнере."""

    def __init__(self, image: str = DEFAULT_IMAGE, timeout: float = 30.0,
                 memory: str = "256m", cpus: str = "1") -> None:
        self.image = image
        self.timeout = timeout
        self.memory = memory
        self.cpus = cpus

    def command(self, name: str) -> list[str]:
        """docker run со всеми ограничениями. Вынесено отдельно ради тестов."""
        return [
            "docker", "run", "--rm", "-i", "--name", name,
            "--network", "none",
            "--read-only", "--tmpfs", "/tmp:size=16m",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", self.memory, "--cpus", self.cpus, "--pids-limit", "64",
            self.image, "python", "-I", "-",
        ]

    def run(self, script: str) -> SandboxResult:
        name = f"llmbench-{uuid.uuid4().hex[:12]}"
        try:
            proc = subprocess.run(
                self.command(name), input=script, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            # Сам docker-клиент убит, но контейнер мог остаться жить — гасим.
            subprocess.run(["docker", "kill", name], capture_output=True)
            return SandboxResult(ok=False, stdout="", stderr="timeout", timed_out=True)
        return SandboxResult(ok=proc.returncode == 0, stdout=proc.stdout, stderr=proc.stderr)


def docker_available(image: str = DEFAULT_IMAGE, pull: bool = True) -> tuple[bool, str]:
    """Есть ли рабочий Docker и нужный образ. Возвращает (да/нет, пояснение).

    Если образа нет и pull=True — скачиваем его один раз заранее, иначе
    первый запуск контейнера упёрся бы в таймаут из-за загрузки образа.
    """
    if shutil.which("docker") is None:
        return False, "команда docker не найдена — установите Docker Desktop"
    info = subprocess.run(["docker", "info"], capture_output=True, **_TEXT)
    if info.returncode != 0:
        return False, "Docker не запущен — откройте Docker Desktop"
    has_image = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    if has_image.returncode != 0:
        if not pull:
            return False, f"нет образа {image} — выполните docker pull {image}"
        print(f"Скачиваю образ {image} (один раз)...")
        pulled = subprocess.run(["docker", "pull", image], capture_output=True, **_TEXT)
        if pulled.returncode != 0:
            return False, f"не удалось скачать {image}: {pulled.stderr.strip()[:200]}"
    return True, "ok"
