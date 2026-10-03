# coloring

Плагін для **Claude Code**: за текстовим описом створює PDF формату A4 з розмальовками для дітей (одна або кілька сторінок).

Джерело кожної сторінки обирається каскадом:

1. **Готова розмальовка** з інтернету.
2. **Зображення, придатне для конвертації**, перетворене на контурний малюнок.
3. **Генерація** через зовнішнє API.

Архітектура описана в [docs/architecture.md](docs/architecture.md).

> Статус: **v0.2**. Працюють `job init`, `analyze`, `thumb`, `lineart` (cleanup/convert) і `pdf`. Пошук, завантаження та генерація поки заглушки з визначеними інтерфейсами.

## Структура

| Шлях | Що це |
|------|-------|
| `.claude-plugin/` | маніфест плагіна та marketplace |
| `skills/coloring-book/SKILL.md` | оркестратор: планування, каскад, звіт |
| `agents/` | субагенти `coloring-searcher`, `image-scout`, `illustrator`, `quality-inspector` |
| `skills/coloring-book/scripts/coloring.py` | toolkit CLI (JSON у stdout) |
| `skills/coloring-book/config.yaml` | налаштування за замовчуванням |
| `skills/coloring-book/reference/` | критерії якості, профілі складності, схема даних |

## Встановлення (локально)

```bash
pip install -r skills/coloring-book/scripts/requirements.txt
```

У Claude Code:

```
/plugin marketplace add <шлях або URL цього репо>
/plugin install coloring@coloring
```

Ключі API задаються змінними середовища (потрібен хоча б один ключ для пошуку і для генерації; Openverse працює без ключа):
`SERPAPI_API_KEY`, `BRAVE_API_KEY`, `OPENAI_API_KEY`, `REPLICATE_API_TOKEN`, `FAL_KEY`.

## Тести

```bash
pip install -r skills/coloring-book/scripts/requirements.txt -r tests/requirements.txt
python3 -m pytest tests
```

Тести генерують синтетичні зображення самі й перевіряють метрики, конвертацію в line-art для всіх профілів складності та верстку PDF.

## Використання

> Зроби розмальовку «тварини ферми» для 4-річної дитини, 5 сторінок, з підписами

Результат з'являється в `output/<дата>_<тема>_<id>/<тема>.pdf`.
