# coloring

Плагін для **Claude Code**: за текстовим описом знаходить в інтернеті готові розмальовки для дітей і збирає з них PDF формату A4 (одна або кілька сторінок).

Плагін лише шукає: генерації зображень і перетворення фото чи кліпарту на контурний малюнок немає. Знайдена розмальовка очищується (поля, рамка з підписами сайту, сірі заливки) і верстається в PDF. Якщо для сторінки нічого не знайшлося, вона пропускається з поясненням.

Архітектура описана в [docs/architecture.md](docs/architecture.md).

> Статус: **v0.5**. Працюють `job init`, `search` (SerpAPI, Brave, Openverse), `extract-images`, `fetch`, `shortlist`, `analyze`, `thumb`, `lineart` (очищення), `review-sheet` і `pdf`.

## Структура

| Шлях | Що це |
|------|-------|
| `.claude-plugin/` | маніфест плагіна та marketplace |
| `skills/coloring-book/SKILL.md` | оркестратор: планування, пошук, перевірка, звіт |
| `agents/` | субагенти `coloring-searcher`, `quality-inspector` |
| `skills/coloring-book/scripts/coloring.py` | toolkit CLI (JSON у stdout) |
| `skills/coloring-book/config.yaml` | налаштування за замовчуванням |
| `skills/coloring-book/reference/` | критерії якості, профілі складності, схема даних, правила для персонажів і показу кандидатів |

## Встановлення (локально)

```bash
pip install -r skills/coloring-book/scripts/requirements.txt
```

У Claude Code:

```
/plugin marketplace add <шлях або URL цього репо>
/plugin install coloring@coloring
```

Ключі API пошуку задаються змінними середовища й необов'язкові (без них працюють сайти розмальовок через WebSearch і Openverse):
`SERPAPI_API_KEY`, `BRAVE_API_KEY`.

## Тести

```bash
pip install -r skills/coloring-book/scripts/requirements.txt -r tests/requirements.txt
python3 -m pytest tests
```

Тести генерують синтетичні зображення самі й перевіряють метрики, очищення line-art для всіх профілів складності, шортлист і верстку PDF.

## Використання

> Знайди розмальовку «тварини ферми» для 4-річної дитини, 5 сторінок, з підписами

Результат з'являється в `output/<дата>_<тема>_<id>/<тема>.pdf`.

Для відомих персонажів (мультфільми, ігри) агенти спершу знаходять офіційне зображення і порівнюють з ним кандидатів. Щоб обрати самому, попросіть «спочатку покажи варіанти»: з'явиться таблиця з еталоном і пронумерованими кандидатами, а далі достатньо назвати номер.
