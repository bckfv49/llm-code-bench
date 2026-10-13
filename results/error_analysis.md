# Анализ провалов (Error Analysis)

Построено по `results/predictions.jsonl` — ответу каждой модели на каждый кейс.
Baseline-заглушки не включены: они читают эталон из промпта.

## gigachat:GigaChat-2-Pro

T1: 32/41 (78%), T2: 18/23 (78%), T3: 27/31 (87%)

### T1 — ошибки статического анализа

| Сложность | Засчитано |
|---|---:|
| basic | 26/33 (79%) |
| hard | 6/8 (75%) |

| Тип ошибки (эталон) | Тип угадан | Засчитано |
|---|---:|---:|
| IndentationError | 2/3 (67%) | 0/3 (0%) |
| TabError | 0/1 (0%) | 0/1 (0%) |
| implicit-str-concat | 0/1 (0%) | 0/1 (0%) |
| unused-import | 2/4 (50%) | 2/4 (50%) |
| TypeError | 4/6 (67%) | 4/6 (67%) |
| SyntaxError | 4/4 (100%) | 4/4 (100%) |
| NameError | 4/4 (100%) | 4/4 (100%) |
| E501 | 2/2 (100%) | 2/2 (100%) |
| bare-except | 3/3 (100%) | 3/3 (100%) |
| dangerous-default-value | 3/3 (100%) | 3/3 (100%) |
| ZeroDivisionError | 2/2 (100%) | 2/2 (100%) |
| singleton-comparison | 3/3 (100%) | 3/3 (100%) |
| assert-on-tuple | 1/1 (100%) | 1/1 (100%) |
| literal-comparison | 1/1 (100%) | 1/1 (100%) |
| IndexError | 1/1 (100%) | 1/1 (100%) |
| AttributeError | 1/1 (100%) | 1/1 (100%) |
| no-method-argument | 1/1 (100%) | 1/1 (100%) |

Проваленные кейсы:

| Кейс | Эталон: тип | Ответ: тип | Эталон: fix | Ответ: fix |
|---|---|---|---|---|
| T1-py-0003 | IndentationError | `IndentationError` | `return x + 1` | — |
| T1-py-0006 | TypeError | `implicit-str-concat` | `print('n=' + str(n))` | `print(f'n={n}')` |
| T1-py-0018 | unused-import | — | — | — |
| T1-py-0019 | unused-import | — | — | — |
| T1-py-0020 | IndentationError | `IndentationError` | `print(i)` | — |
| T1-py-0021 | IndentationError | `SyntaxError` | `pass` | `pass` |
| T1-py-0024 | TypeError | `implicit-str-concat` | `result = [1, 2] + list((3, 4))` | `result = [1, 2] + list((3, 4))` |
| T1-py-0035 | TabError | `IndentationError` | `return 1` | `return 1` |
| T1-py-0038 | implicit-str-concat | `SyntaxError` | `COLUMNS = ["id", "name", "email"]` | `COLUMNS = ["id", "name", "email"]` |

**Ловушки, в которые попала модель:**

- **T1-py-0035** — отступ табом среди пробелов: не просто IndentationError, а более конкретный TabError
- **T1-py-0038** — пропущенная запятая склеивает две строки в одну — код валиден, ошибки при запуске нет

### T2 — поиск уязвимостей

| Домен | CWE верный | Засчитано |
|---|---:|---:|
| ml | 3/5 (60%) | 3/5 (60%) |
| system | 4/6 (67%) | 4/6 (67%) |
| web | 11/12 (92%) | 11/12 (92%) |

**Путаница CWE** — 5 из 23 кейсов:

Колонка «Объяснение модели» показывает, поняла ли модель суть уязвимости, даже если номер CWE неверный.

| Кейс | Домен | Эталон | Допустимо также | Ответ модели | Объяснение модели |
|---|---|---|---|---|---|
| T2-py-0009 | web | CWE-918 | — | CWE-89 | Direct use of unvalidated user input in an HTTP request can lead to injection vulnerabilities if the URL parameter is malicious. |
| T2-py-0015 | ml | CWE-502 | — | CWE-78 | The use of `allow_pickle=True` in `np.load()` enables unpickling of arbitrary objects, which can lead to remote code execution vulnerabilities. |
| T2-py-0016 | ml | CWE-94 | CWE-829, CWE-494 | CWE-89 | The use of `trust_remote_code=True` allows execution of potentially malicious code from untrusted sources, leading to remote code execution vulnerabilities. |
| T2-py-0019 | system | CWE-367 | CWE-362 | CWE-73 | The code uses an unvalidated file path directly in the open() function, which could lead to path traversal vulnerabilities. |
| T2-py-0020 | system | CWE-362 | CWE-366, CWE-667 | CWE-327 | The code modifies a shared variable without proper synchronization, leading to potential race conditions and inconsistent state. |

**Строки с уязвимостью найдены не полностью или с лишними** — 2 кейсов:

| Кейс | Эталонные строки | Ответ модели |
|---|---|---|
| T2-py-0009 | [6] | [5] |
| T2-py-0019 | [4, 5] | [5] |

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
| T3-py-0025 | hard | insertion sort -> sorted(key) (stable, no mutation) | тесты прошли, но код не стал проще: строк 8 → 10, узлов AST 103 → 101 |
| T3-py-0028 | hard | concat loop skipping None -> join (keep 0) | тесты упали: AssertionError |

**Ловушки, в которые попала модель:**

**T3-py-0023** — loop with >= -> max over reversed (ties)

- Ловушка: при равных score исходник возвращает ПОСЛЕДНИЙ элемент (>=), а max() — первый
- Результат: тесты упали: AssertionError

Ответ модели:

```python
def latest_best(runs):
    return max(runs, key=lambda r: r['score'], default=None)
```

**T3-py-0025** — insertion sort -> sorted(key) (stable, no mutation)

- Ловушка: names.sort() изменяет входной список; sorted() без key сортирует с учётом регистра
- Результат: тесты прошли, но код не стал проще: строк 8 → 10, узлов AST 103 → 101

Ответ модели:

```python
def sort_names(names):
    names_list = list(names)
    
    # Implementing case-insensitive insertion sort
    for i in range(1, len(names_list)):
        current_name = names_list[i]
        j = i - 1
        
        # Move elements of names_list[0..i-1] that are greater than current_name
        # to one position ahead of their current position
        while j >= 0 and names_list[j].lower() > current_name.lower():
            names_list[j + 1] = names_list[j]
            j -= 1
            
        # Place current_name at correct position
        names_list[j + 1] = current_name
    
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

- IndentationError: 3
- TypeError: 2
- unused-import: 2
- TabError: 1
- implicit-str-concat: 1

**T2** — по категории «CWE»:

- CWE-918: 1
- CWE-502: 1
- CWE-94: 1
- CWE-367: 1
- CWE-362: 1

**T3** — по категории «паттерн»:

- manual accumulation -> sum(): 1
- loop with >= -> max over reversed (ties): 1
- insertion sort -> sorted(key) (stable, no mutation): 1
- concat loop skipping None -> join (keep 0): 1
