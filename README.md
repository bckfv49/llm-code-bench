# LLM Code Bench

Открытый бенчмарк для оценки больших языковых моделей в задачах
**анализа существующего кода** (code-to-code), а не только генерации с нуля.

Курсовая работа, 1 семестр. Тема: «Разработка комплексного бенчмарка
для оценки качества LLM в задачах анализа программного обеспечения».

## Зачем это нужно

Существующие бенчмарки (HumanEval, MBPP) проверяют только `text -> code`:
модель пишет функцию по её описанию. В реальной разработке важнее другое:
починить чужой баг, отрефакторить легаси, объяснить алгоритм, оценить
влияние правки на соседние модули. Мы собираем датасет и стенд именно для
таких задач.

## Модули задач

| ID | Название | Вход | Метрика |
|----|----------|------|---------|
| T1 | Lint / static-analysis fix | код с синтаксической ошибкой или warning | Exact Match фикса, Accuracy типа ошибки |
| T2 | Security bug detection | код с известной уязвимостью (CWE) | Precision/Recall строк, F1 по CWE |
| T3 | Refactoring | легаси-код | unit-тесты + снижение сложности |
| T4 | Impact analysis | монорепо + запрос на изменение | Recall покрытия графа вызовов |
| T5 | Algorithm explanation | оптимизированный код без комментариев | BERTScore / ROUGE-L против эталона |

Сегодня в репозитории поднят **только T1** — сквозной MVP, чтобы стенд
крутился end-to-end. Остальные будут добавляться по мере роадмапа.

## Пайплайн

```
data source -> jsonl dataset -> harness (LLM client) -> evaluator -> leaderboard
```

Все LLM (GigaChat, OpenAI, локальные) прячутся за общим интерфейсом
`LLMClient`. Промпты стандартизированы, чтобы условия были равными.
Функциональные проверки (T3) позже пойдут в Docker-песочницу.

## Быстрый старт

```bash
pip install -r requirements.txt
python -m scripts.run_demo
```

Скрипт прогонит T1 (33 кейса) через реальную модель GigaChat + два
калиброванных baseline'а и напечатает лидерборд. Результаты сохранятся
в папку `results/`.

Для работы GigaChat нужен ключ. Создай файл `.env` в корне проекта:

```
GIGACHAT_CREDENTIALS=твой_Authorization_key
```

Ключ выдаётся на https://developers.sber.ru/studio на бесплатном тарифе Freemium.
Файл `.env` **не** коммитится в git — он в `.gitignore`.

Если ключа нет — просто закомментируй строку `GigaChatClient(),` в
`scripts/run_demo.py`, и стенд крутится на baseline-моделях без сети.

## Актуальные результаты

Прогон на 33 handcrafted-кейсах T1 (см. `results/leaderboard.txt` и
`results/run.json`):

| Модель | EM | TypeAcc | Pass | Задержка |
|---|---:|---:|---:|---:|
| gigachat:GigaChat-2-Pro | 69.2% | **78.8%** | **63.6%** | ~570 мс |
| noisy-baseline (p=0.5) | 53.8% | 60.6% | 48.5% | ~0 |
| noisy-baseline-weak (p=0.2) | 19.2% | 24.2% | 18.2% | ~0 |

GigaChat строго обгоняет калиброванный baseline по всем метрикам —
стенд действительно измеряет качество.

**Ограничения Exact Match и multiple_valid.** У некоторых типов ошибок
допустимо несколько семантически эквивалентных фиксов: `bare-except`
можно закрыть любым классом исключения (`Exception`, `ValueError`,
`KeyError`), `E501` можно переносить строку разными способами,
`ZeroDivisionError` — защищать через `if`, `try` или тернарный оператор.
Для таких кейсов в `metadata` установлено `multiple_valid: true` —
evaluator не считает Exact Match, только Type Accuracy, и не наказывает
модель за форматирование. Это временное решение до внедрения мягких
метрик (CodeBLEU, AST-diff, functional equivalence через unit-тесты),
которые стоят в roadmap на недели 9–10.

**Про калиброванные baseline'ы.** `noisy-baseline` — это не имитация
плохой нейросети, а честная лестница: с вероятностью `p_correct` модель
даёт правильный ответ (читая oracle-блок из промпта), иначе — случайный
из фиксированных списков. GigaChat oracle-блок **не получает**, оценивается
на чистом промпте. Baseline'ы нужны, чтобы (а) убедиться, что стенд
чувствителен к качеству и (б) видеть, где реальная модель проседает
относительно контролируемого эталона.

## Структура

```
llm-code-bench/
├── README.md
├── requirements.txt
├── .env                         # ключ GigaChat (не в git)
├── data/
│   └── task1_lint/
│       └── samples.jsonl        # 33 handcrafted-кейса
├── src/
│   ├── schema.py                # pydantic-модели кейса и предсказания
│   ├── harness.py               # LLMClient + GigaChat + NoisyModel + EchoModel
│   ├── evaluator.py             # метрики + прогон (oracle только для NoisyModel)
│   └── tasks/
│       ├── task1_lint.py        # T1 — реализовано
│       ├── task2_security.py    # T2 — заглушка
│       ├── task3_refactor.py    # T3 — заглушка
│       ├── task4_impact.py      # T4 — заглушка
│       └── task5_explain.py     # T5 — заглушка
├── scripts/
│   ├── run_demo.py              # точка входа для демо
│   ├── validate_dataset.py      # проверка JSONL на схему и дубли
│   └── debug_gigachat.py        # отладка одного кейса на GigaChat
├── results/                     # сохранённые лидерборды прогонов
│   ├── leaderboard.txt
│   └── run.json
└── tests/
    └── test_smoke.py            # 7 smoke-тестов
```

## Тесты

```bash
python -m pytest tests/ -q
```

Семь smoke-тестов: загрузка датасета, работа парсера, EchoModel даёт 100%
на oracle-промпте, NoisyModel всегда хуже эталона, лидерборд рендерится,
`case_id` уникальны, валидатор принимает актуальный датасет.

## Роадмап

- [x] MVP T1 + сквозной evaluator на dummy-моделях
- [x] Расширение стартового датасета T1 до 33 кейсов
- [x] Валидатор JSONL-датасета (`scripts/validate_dataset.py`)
- [x] Подключение реальной модели GigaChat через официальный SDK
- [x] Сохранение результатов прогона в `results/` (leaderboard + JSON)
- [x] Калиброванный `NoisyModel` (p_correct) как честная лестница baseline'ов
- [x] Изоляция oracle-блока: только для NoisyModel, GigaChat получает чистый промпт
- [x] Флаг `multiple_valid` для многовариантных фиксов + чистка датасета по ревью
- [ ] Скрипты сбора кейсов из `git blame` (bug-fix pairs)
- [ ] Мутационное тестирование для T1
- [ ] Подключение OpenAI и локальных моделей для сравнения
- [ ] Мягкие метрики (CodeBLEU, AST-diff) в дополнение к Exact Match
- [ ] T2: сбор CWE-кейсов из GitHub Advisories
- [ ] T3: unit-based verifier + Docker sandbox
- [ ] T4: построение call-graph через `tree-sitter`
- [ ] T5: BERTScore, эталонные описания
- [ ] Bootstrap-анализ значимости различий моделей
- [ ] Дедупликация с обучающими выборками через эмбеддинги
- [ ] Публикация датасета под MIT

## Лицензия

MIT