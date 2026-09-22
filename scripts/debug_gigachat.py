"""
Дебаг: сначала показывает список доступных на аккаунте моделей,
потом пробует прогнать первый кейс на первой из них.
Запуск: python -m scripts.debug_gigachat
"""

from dotenv import load_dotenv
load_dotenv()

import os
from gigachat import GigaChat
from src.tasks.task1_lint import build_prompt, load_cases
from pathlib import Path

DATASET = Path(__file__).resolve().parent.parent / "data" / "task1_lint" / "samples.jsonl"


def main() -> None:
    creds = os.environ["GIGACHAT_CREDENTIALS"]
    with GigaChat(credentials=creds, verify_ssl_certs=False) as giga:
        models = giga.get_models().data
        print("Доступные модели:")
        for m in models:
            print(f"  - {m.id_}")

        if not models:
            print("Список пустой — проблема с тарифом.")
            return

        model_name = models[0].id_
        print(f"\nПробую модель: {model_name}\n")

        case = load_cases(DATASET)[0]
        prompt = build_prompt(case, include_oracle=False)

        # Пересоздаём клиент уже с конкретной моделью
        giga2 = GigaChat(credentials=creds, model=model_name, verify_ssl_certs=False)
        response = giga2.chat(prompt)
        raw = response.choices[0].message.content

        print("=" * 60)
        print("RAW ANSWER:")
        print("=" * 60)
        print(raw)
        print("=" * 60)
        print(f"EXPECTED TYPE: {case.expected['error_type']}")
        print(f"EXPECTED FIX:  {case.expected['fix']}")


if __name__ == "__main__":
    main()