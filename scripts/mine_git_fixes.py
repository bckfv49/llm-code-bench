"""
Сбор кандидатов в кейсы T1 из git-истории чужого репозитория.

Ручной датасет не масштабируется, а в любом живом репозитории уже лежат
тысячи настоящих багфиксов. Ищем коммиты с fix/bug в сообщении и берём из
них однострочные правки: ровно одна удалённая и ровно одна добавленная
строка в ханке. Почему только такие — формат ответа T1 это одна строка
`FIX:`, многострочный рефакторинг в него не укладывается (он поедет в T3).

Про git blame: классический рецепт «blame строку, найди коммит-виновник»
даёт то же самое, но требует прохода по каждой строке каждого файла.
`git log -p` отдаёт готовые пары «до/после» одним вызовом, поэтому берём его.

Тип ошибки из диффа не выводится — его ставит человек. Поэтому кандидаты
идут в отдельный файл с `needs_review: true` и НЕ подмешиваются в
samples.jsonl автоматически.

    python -m scripts.mine_git_fixes /path/to/repo -o data/task1_lint/mined.jsonl
    python -m scripts.mine_git_fixes . --limit 500 --ext .py .js
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Коммиты-багфиксы: смотрим на сообщение. Грубо, но именно так делают
# в статьях по майнингу bug-fix pairs (напр. датасет ManySStuBs4J).
FIX_MESSAGE_RE = re.compile(r"\b(fix(e[sd])?|bug|repair|patch|correct)\b", re.I)

# Язык по расширению — нужен для поля language в схеме.
LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".java": "java", ".go": "go", ".cpp": "cpp", ".c": "c", ".cs": "csharp",
}


def _git(repo: Path, *args: str) -> str:
    """git в указанном репозитории. Падает с понятным сообщением."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} -> {result.stderr.strip()}")
    return result.stdout


def iter_single_line_fixes(diff: str, exts: list[str]):
    """Однострочные правки из вывода `git log -p`.

    Отдаёт (sha, message, path, before, after, context) для каждого ханка,
    где ровно один минус и ровно один плюс.
    """
    sha = message = path = ""
    keep_file = False
    hunk: list[str] = []
    context: list[str] = []

    def flush():
        """Ханк закончился — годится ли он в кейс?"""
        minus = [ln[1:] for ln in hunk if ln.startswith("-")]
        plus = [ln[1:] for ln in hunk if ln.startswith("+")]
        if len(minus) == 1 and len(plus) == 1 and minus[0].strip() and keep_file:
            return (sha, message, path, minus[0], plus[0], "\n".join(context))
        return None

    for line in diff.split("\n"):
        if line.startswith("\x00"):  # наш разделитель коммитов: \0<sha>\0<subject>
            got = flush()
            if got:
                yield got
            hunk, context = [], []
            _, sha, message = line.split("\x00", 2)
        elif line.startswith("+++ b/"):
            got = flush()
            if got:
                yield got
            hunk, context = [], []
            path = line[6:]
            keep_file = any(path.endswith(e) for e in exts)
        elif line.startswith("@@"):
            got = flush()
            if got:
                yield got
            hunk, context = [], []
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            hunk.append(line)
        elif line.startswith(" "):
            context.append(line[1:])
    got = flush()
    if got:
        yield got


def mine(repo: Path, limit: int, exts: list[str]) -> list[dict]:
    """Возвращает кандидатов в кейсы T1 (без error_type — его ставит человек)."""
    diff = _git(
        repo, "log", f"-n{limit}", "-p", "--no-merges", "--unified=3",
        "--format=%x00%H%x00%s",
    )
    cases: list[dict] = []
    for sha, message, path, before, after, context in iter_single_line_fixes(diff, exts):
        if not FIX_MESSAGE_RE.search(message):
            continue
        ext = Path(path).suffix
        cases.append({
            "case_id": f"T1-git-{sha[:8]}-{len(cases) + 1:03d}",
            "task": "T1",
            "language": LANG_BY_EXT.get(ext, ext.lstrip(".") or "unknown"),
            "prompt": "",
            # error_type пустой намеренно: из диффа его не вывести.
            "expected": {"error_type": "", "fix": after.strip()},
            "metadata": {
                "snippet": before,
                "context": context,
                "source": "git-history",
                "repo": str(repo),
                "commit": sha,
                "commit_subject": message,
                "path": path,
                "needs_review": True,  # без разметки типа в samples.jsonl не берём
            },
        })
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description="Сбор bug-fix пар из git-истории")
    ap.add_argument("repo", type=Path, help="путь к git-репозиторию")
    ap.add_argument("-o", "--out", type=Path, help="куда писать JSONL (иначе stdout)")
    ap.add_argument("--limit", type=int, default=300, help="сколько коммитов смотреть")
    ap.add_argument("--ext", nargs="+", default=[".py"], help="расширения файлов")
    args = ap.parse_args()

    try:
        cases = mine(args.repo, args.limit, args.ext)
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    text = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"[OK] {len(cases)} кандидатов -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    print(
        f"Кандидатов: {len(cases)}. error_type нужно разметить вручную "
        "перед переносом в samples.jsonl.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
