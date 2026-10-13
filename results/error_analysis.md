# Анализ провалов (Error Analysis)

Построено по `results/predictions.jsonl` — ответу каждой модели на каждый кейс.
Baseline-заглушки не включены: они читают эталон из промпта.

## gigachat:GigaChat-2-Pro

T1: 21/33 (64%), T2: 17/23 (74%), T3: 27/31 (87%)

### T1 — ошибки статического анализа

| Тип ошибки (эталон) | Тип угадан | Засчитано |
|---|---:|---:|
| unused-import | 4/4 (100%) | 0/4 (0%) |
| IndentationError | 1/3 (33%) | 0/3 (0%) |
| mutable-default | 0/3 (0%) | 0/3 (0%) |
| comparison-with-none | 1/3 (33%) | 1/3 (33%) |
| SyntaxError | 3/3 (100%) | 3/3 (100%) |
| NameError | 4/4 (100%) | 4/4 (100%) |
| E501 | 2/2 (100%) | 2/2 (100%) |
| TypeError | 6/6 (100%) | 6/6 (100%) |
| bare-except | 3/3 (100%) | 3/3 (100%) |
| ZeroDivisionError | 2/2 (100%) | 2/2 (100%) |

Проваленные кейсы:

| Кейс | Эталон: тип | Ответ: тип | Эталон: fix | Ответ: fix |
|---|---|---|---|---|
| T1-py-0002 | unused-import | `unused-import` | — | `print('hello')` |
| T1-py-0003 | IndentationError | `indentation-error` | `return x + 1` | `python` |
| T1-py-0008 | mutable-default | `mutable-default-argument` | `def add(x, acc=None):` | `def add(x, acc=None):` |
| T1-py-0010 | comparison-with-none | `comparison-to-none-should-be-is` | `if x is None:` | `if x is None:` |
| T1-py-0017 | unused-import | `unused-import` | — | `print('hi')` |
| T1-py-0018 | unused-import | `unused-import` | — | `x = 42` |
| T1-py-0019 | unused-import | `unused-import` | — | `print('nope')` |
| T1-py-0020 | IndentationError | `IndentationError` | `print(i)` | — |
| T1-py-0021 | IndentationError | `syntax-error` | `pass` | `class Foo:\n    pass` |
| T1-py-0027 | mutable-default | `mutable-default-argument` | `def build(x, cfg=None):` | `def build(x, cfg=None):` |
| T1-py-0028 | mutable-default | `mutable-default-argument` | `def tag(x, seen=None):` | `def tag(x, seen=None):` |
| T1-py-0029 | comparison-with-none | `comparison-to-none-should-be-is` | `if x is not None:` | `if x is not None:` |

### T2 — поиск уязвимостей

| Домен | CWE верный | Засчитано |
|---|---:|---:|
| ml | 3/5 (60%) | 3/5 (60%) |
| system | 3/6 (50%) | 3/6 (50%) |
| web | 11/12 (92%) | 11/12 (92%) |

**Путаница CWE** — 6 из 23 кейсов:

| Кейс | Домен | Эталон | Допустимо также | Ответ модели |
|---|---|---|---|---|
| T2-py-0009 | web | CWE-918 | — | CWE-89 |
| T2-py-0015 | ml | CWE-502 | — | CWE-78 |
| T2-py-0016 | ml | CWE-94 | CWE-829, CWE-494 | CWE-89 |
| T2-py-0019 | system | CWE-367 | CWE-362 | CWE-22 |
| T2-py-0020 | system | CWE-362 | CWE-366, CWE-667 | CWE-327 |
| T2-py-0021 | system | CWE-476 | CWE-252 | CWE-654 |

**Строки с уязвимостью найдены не полностью или с лишними** — 1 кейсов:

| Кейс | Эталонные строки | Ответ модели |
|---|---|---|
| T2-py-0009 | [6] | [5] |

### T3 — рефакторинг

| Сложность | Тесты прошли | Засчитано |
|---|---:|---:|
| basic | 21/22 (95%) | 21/22 (95%) |
| hard | 7/9 (78%) | 6/9 (67%) |

Проваленные кейсы:

| Кейс | Сложность | Паттерн | Причина |
|---|---|---|---|
| T3-py-0010 | basic | manual accumulation -> sum() | тесты упали: AssertionError |
| T3-py-0023 | hard | loop with >= -> max over reversed (ties) | тесты упали: AssertionError |
| T3-py-0025 | hard | insertion sort -> sorted(key) (stable, no mutation) | тесты прошли, но код не стал проще: строк 8 → 10, узлов AST 103 → 98 |
| T3-py-0028 | hard | concat loop skipping None -> join (keep 0) | тесты упали: AssertionError |

**Ловушки, в которые попала модель:**

**T3-py-0023** — loop with >= -> max over reversed (ties)

- Ловушка: при равных score исходник возвращает ПОСЛЕДНИЙ элемент (>=), а max() — первый
- Результат: тесты упали: AssertionError

Ответ модели:

```python
def latest_best(runs):
    return max(runs, key=lambda x: x['score'], default=None)
```

**T3-py-0025** — insertion sort -> sorted(key) (stable, no mutation)

- Ловушка: names.sort() изменяет входной список; sorted() без key сортирует с учётом регистра
- Результат: тесты прошли, но код не стал проще: строк 8 → 10, узлов AST 103 → 98

Ответ модели:

```python
def sort_names(names):
    names_list = list(names)
    
    # Implementing case-insensitive insertion sort
    for i in range(1, len(names_list)):
        current_name = names_list[i]
        position = i
        
        # Move elements of the sorted segment forward if greater than current element
        while position > 0 and names_list[position - 1].lower() > current_name.lower():
            names_list[position] = names_list[position - 1]
            position -= 1
            
        # Place current element at correct position
        names_list[position] = current_name
    
    return names_list
```

**T3-py-0028** — concat loop skipping None -> join (keep 0)

- Ловушка: фильтр `if p` выбрасывает и 0, а исходник пропускает только None
- Результат: тесты упали: AssertionError

Ответ модели:

```python
def format_address(parts):
    filtered_parts = filter(None, parts)
    return ', '.join(map(str, filtered_parts))
```


## Провалы всех моделей

Пока подключена одна реальная модель, поэтому здесь её провалы. С подключением второй модели останутся только кейсы, которые не решила ни одна.

**T1** — по категории «тип ошибки»:

- unused-import: 4
- IndentationError: 3
- mutable-default: 3
- comparison-with-none: 2

**T2** — по категории «CWE»:

- CWE-918: 1
- CWE-502: 1
- CWE-94: 1
- CWE-367: 1
- CWE-362: 1
- CWE-476: 1

**T3** — по категории «паттерн»:

- manual accumulation -> sum(): 1
- loop with >= -> max over reversed (ties): 1
- insertion sort -> sorted(key) (stable, no mutation): 1
- concat loop skipping None -> join (keep 0): 1
