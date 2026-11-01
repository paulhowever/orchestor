# Рынок и аналоги `/orchestrate`

Дата сбора: 2026-11-01. Звёзды, лицензии и даты последнего пуша — из GitHub API на эту дату. Всё остальное — со страниц, на которые стоит ссылка. Что не удалось проверить по первоисточнику, помечено «не проверено».

## Коротко

- Почти всё, что делает `/orchestrate` по частям, **уже есть** — и в самом Claude Code, и в десятках сторонних инструментов: параллельные сессии, git worktree на задачу, выбор модели, PR и авто-фикс CI, архив.
- Ближайший по смыслу конкурент — **не сторонний, а официальный**: Claude Projects (бета) и Agent view (research preview). Они закрывают «разбить на параллельные сессии, дать каждой свою модель, следить за PR» без всякого скила.
- Реально редкое у `/orchestrate`: **жёсткие правила посадки** (один «да» = одно именованное действие, «да» внутри отчётов/файлов не считается), **проверка Done перед архивом** (чистый worktree, нет незамёрдженных коммитов, CI зелёный в CI), **память-очередь как кэш со сверкой по `list_sessions` и git**, **самоочистка оркестратора**. Ни у одного найденного аналога все четыре вместе я не нашёл (это «не нашёл», а не доказательство отсутствия).
- Главный риск позиционирования: это скил для **одного конкретного окружения** (Claude desktop, вкладка Code, инструмент `start_session`), а рынок уходит в сторону встроенных функций Anthropic.

## 1. Что есть у Claude Code из коробки

| Возможность | Что делает | Как запускает работу | Модель под задачу | Гейт «пуш по да» | Архив/очистка | Ссылка |
|---|---|---|---|---|---|---|
| Subagents | Помощники внутри одной сессии | Свой контекст; `isolation: worktree` — временный worktree | Да: `model` во frontmatter или параметр вызова | Отдельного нет; режимы разрешений (`plan`, `dontAsk` и т.д.) | Worktree без изменений удаляется сам | [sub-agents](https://code.claude.com/docs/en/sub-agents), [worktrees](https://code.claude.com/docs/en/worktrees) |
| Agent teams (экспериментально, выключено по умолчанию) | Лид + тиммейты с общим списком задач и перепиской | Отдельные сессии Claude, in-process или панели tmux/iTerm2; **без worktree** | Да: в промпте, в определении субагента или через env | Хуки `TeammateIdle`/`TaskCompleted`; план-апрув у лида | Каталог команды чистится при завершении сессии | [agent-teams](https://code.claude.com/docs/en/agent-teams) |
| Agent view (`claude agents`, research preview) | Один экран для фоновых сессий | `claude --bg`; сессия сама уходит в свой worktree | Да: `--model`, `--effort` на диспетчер или сессию | Фоновые сессии пушат ветку, но **не пушат в main, не форс-пушат и не мёрджат** | `claude rm`; удаление отказывается при непушнутых коммитах | [agent-view](https://code.claude.com/docs/en/agent-view) |
| `/batch` (встроенный скил) | Один большой change → 5–30 субагентов в worktree | Субагенты, каждый открывает PR | Не описано | Нет | Как у субагентов | [agents](https://code.claude.com/docs/en/agents) |
| Dynamic workflows | Скрипт запускает много субагентов и перекрёстно проверяет | Субагенты по скрипту | Не проверено | Нет | Нет | [agents](https://code.claude.com/docs/en/agents) |
| Cross-session messaging | Сессии пишут друг другу | Сокет на машине / через Remote Control | — | Сообщение от другой сессии **не заменяет** согласие пользователя | — | [cross-session-messaging](https://code.claude.com/docs/en/cross-session-messaging) |
| Desktop: параллельные сессии | Сессии с worktree, split view, task cards «Start / Do it here», модель и effort на сессию | Отдельные сессии в приложении | Да | Auto-fix CI и «Merge when ready» включает пользователь | Архив вручную; авто-архив после merge/close PR | [desktop](https://code.claude.com/docs/en/desktop) |
| **Projects** (публичная бета, Pro/Max/Ultra) | Один разговор-координатор, на каждую задачу «тред» (облачная сессия) | Облако; по запросу — на вашем компьютере через Remote Control | Да: Thread model/effort в настройках, «эту задачу — меньшей моделью» | Кнопки «Merge it», «Fix CI»; PR под авто-фиксом | Не проверено | [claude-projects](https://code.claude.com/docs/en/claude-projects) |

Projects держит **память проекта** (`MEMORY.md`, решения, ловушки) и инструкции проекта — то есть «память очереди» там тоже есть, только внутри облака Anthropic ([claude-projects](https://code.claude.com/docs/en/claude-projects)).

## 2. Сторонние инструменты

Звёзды/лицензия/активность — GitHub API на 2026-11-01.

| Инструмент | Что делает | Запуск работы | Модель под задачу | Гейт «пуш по да» | Архив/очистка | Дайджест | Память очереди | Звёзды · лицензия · активность |
|---|---|---|---|---|---|---|---|---|
| [Claude Squad](https://github.com/smtg-ai/claude-squad) | TUI для нескольких агентов | tmux-сессия + git worktree на сессию | Выбор программы/профиля на запуск (claude, codex, gemini, aider…) — выбор агента, не авто-подбор | Коммит и пуш — ручные клавиши `c`/`s` | Не описано | Нет | Нет | 8 713 · AGPL-3.0 · пуш 2026-08-20 |
| [Vibe Kanban](https://github.com/BloopAI/vibe-kanban) | Канбан-доска задач для агентов | Workspace с веткой, терминалом и dev-сервером на задачу | Выбор агента (10+), не авто-подбор | Вы смотрите diff и мёрджите PR на GitHub | Чистка осиротевших/просроченных worktree | Доска | Доска (в приложении) | 28 548 · Apache-2.0 · пуш 2026-10-29. **README: «sunsetting»** |
| [Nimbalyst (бывш. Crystal)](https://github.com/Nimbalyst/nimbalyst) | Визуальное рабочее пространство для Claude Code/Codex | Параллельные сессии, worktree опционально, канбан сессий | Выбор агента | Ревью изменений в UI | Не проверено | Канбан | Не проверено | 2 010 · MIT · пуш 2026-10-31. Старый [Crystal](https://github.com/stravu/crystal): 3 131 · MIT · заморожен 2026-02-26 |
| [Emdash](https://github.com/generalaction/emdash) | Десктоп для параллельных агентов, задачи из Linear/Jira/GitHub | Worktree + ветка на задачу | Выбор провайдера | Diff → PR → CI → merge в одном месте, нажимает человек | Не проверено | Нет | Нет | 6 136 · Apache-2.0 · пуш 2026-10-30 |
| [Conductor](https://www.conductor.build/) | Mac-приложение: агенты параллельно, ревью и merge | Свой workspace на агента | Claude Code / Codex / Cursor — выбор агента | Ревью и merge вручную | Не проверено | Обзор «кто что делает» | Не проверено | Закрытый код, только macOS. [Сравнение](https://munderdiffl.in/blog/best-claude-code-multi-agent-tools/) |
| [Paradev (бывш. Superset)](https://github.com/superset-sh/superset) | «Агентная IDE», 100+ агентов параллельно | По описанию репо — параллельный запуск | Не проверено | Не проверено | Не проверено | Не проверено | Не проверено | 15 804 · NOASSERTION · пуш 2026-11-01 |
| [dmux](https://github.com/standardagents/dmux) | Мультиплексор агентов на worktree | tmux + worktree | Выбор агента | Не проверено | Не проверено | Нет | Нет | 1 814 · MIT · пуш 2026-08-16 |
| [ccmanager](https://github.com/kbwo/ccmanager) | Менеджер сессий Claude Code/Gemini/Codex/Cursor/Copilot | Сессии, без tmux | Выбор агента | Не проверено | Не проверено | Нет | Нет | 1 276 · MIT · пуш 2026-10-27 |
| [Mux (coder)](https://github.com/coder/mux) | Десктоп для изолированной параллельной разработки | По описанию репо — изоляция | Не проверено | Не проверено | Не проверено | Не проверено | Не проверено | 2 061 · AGPL-3.0 · пуш 2026-11-01 |
| [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) | Мульти-агентная надстройка для Claude Code: `/team`, autopilot, verify/fix | tmux-панели с воркерами; worktree для воркеров — опционально, в разработке | **Да**: Haiku для простого, Opus для сложного | Verify-режим требует доказательств (тесты, build, lint, typecheck) — гейт качества, не гейт пуша | Воркеры завершаются сами | Логи/реплеи сессий | Да: паттерны → скилы, саммари сессий | 40 475 · MIT · пуш 2026-11-01 |
| [ruflo](https://github.com/ruvnet/ruflo) | Роевая оркестрация с роутером и векторной памятью | Хуки + MCP, «рой» агентов | **Да**: роутер по задаче (цифры точности — самореклама README, не проверены) | Не проверено | Не проверено | Панель роя | Да: AgentDB, ReasoningBank | 80 451 · MIT · пуш 2026-11-01 |
| [ralph-orchestrator](https://github.com/mikeyobrien/ralph-orchestrator) | Оркестрация по технике Ralph Wiggum | Не проверено | Не проверено | Не проверено | Не проверено | Не проверено | Не проверено | 3 191 · MIT · пуш 2026-10-31 |
| [claude_code_agent_farm](https://github.com/Dicklesworthstone/claude_code_agent_farm) | 20+ агентов Claude Code параллельно | Не проверено | Не проверено | Не проверено | Не проверено | Не проверено | Не проверено | 924 · NOASSERTION · пуш 2026-09-21 |
| [overstory](https://github.com/jayminwest/overstory) | Мульти-агентная оркестрация с адаптерами | Не проверено | Не проверено | Не проверено | Не проверено | Не проверено | Не проверено | 1 313 · MIT · **архивирован** (последний пуш 2026-05-28) |

### Скилы «поменьше», ближе всего по форме к `/orchestrate`

| Скил | Что делает | Запуск | Модель | Гейты | Очистка | Ссылка · звёзды · лицензия |
|---|---|---|---|---|---|---|
| orchestrating-parallel-work (dorkos) | Плейбук: волны субагентов, потом посадка веток | Несколько вызовов Agent в одном сообщении, `isolation: "worktree"`, лимит ~4 worktree | Не подбирает модель, подбирает **тип агента** | Отдельный агент-ревьюер до PR; полный прогон тестов после rebase; проверка, что auto-merge взведён | Worktree удаляется только когда содержимое точно в `main`; грязные/непушнутые не трогаются | [SKILL.md](https://github.com/dork-labs/dorkos/blob/main/.claude/skills/orchestrating-parallel-work/SKILL.md) · 12 · MIT |
| parallel-worktrees | Параллельные субагенты в worktree и синхронизация | Скрипты spawn/cleanup/sync | Нет | Нет | Скрипт cleanup | [репо](https://github.com/SpillwaveSolutions/parallel-worktrees) · 16 · лицензия не указана |
| worktree-spawn-skill | Worktree с контекстом сессии, Claude Code и Codex | Скрипт | Нет | Нет | Нет | [репо](https://github.com/bookdisco/worktree-spawn-skill) · 1 · лицензия не указана |
| claude-code-trees | Python-библиотека управления экземплярами на worktree | SDK + SQLite | Нет | Нет | Нет | [репо](https://github.com/rizome-dev/claude-code-trees) · 2 · MIT · пуш 2025-08 |

Общие каталоги, где `/orchestrate` стоит светиться: [anthropics/skills](https://github.com/anthropics/skills) (186 055 звёзд), [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) (57 011), [wshobson/agents](https://github.com/wshobson/agents) (42 063 · MIT, маркетплейс плагинов). Сами списки внутри этих каталогов я не разбирал (WebFetch не показал таблицу ресурсов awesome-claude-code), так что есть ли там прямые аналоги — не проверено.

### Облачные фоновые агенты (другая категория)

| Продукт | Запуск | Изоляция | Модель | PR | Ссылка |
|---|---|---|---|---|---|
| Cursor Cloud/Background Agents | iOS, веб, десктоп, Slack, GitHub, Linear, API | Облачная VM на агента | Из курируемого набора | Ветка, PR в каждый репо, артефакты (скриншоты/видео/логи) | [docs](https://cursor.com/docs/background-agent) |
| Codex cloud | Задачи в песочнице OpenAI | Песочница на задачу | Не проверено | Черновик PR (по вторичному источнику) | [Tembo](https://tembo.io/blog/devin-alternatives-2025) (первоисточник за редиректом не открылся) |
| Devin, Jules | Автономные облачные агенты, итог — PR | Облако | Не проверено | PR на ревью | [обзор](https://techsy.io/blog/background-coding-agents-compared) (листикл, детали не проверены) |

Они решают «выполни задачу в облаке и пришли PR», а не «расщепи пачку задач из чата и веди их у меня на Mac», поэтому прямыми конкурентами не считаю.

## 3. Что уже есть у всех (не подавать как фишку)

- Параллельные сессии/агенты, у каждого свой worktree и ветка: Claude Code ([worktrees](https://code.claude.com/docs/en/worktrees)), Claude Squad, Vibe Kanban, Emdash.
- Выбор модели под задачу: у Claude Code на субагента, тиммейта и сессию ([sub-agents](https://code.claude.com/docs/en/sub-agents), [agent-teams](https://code.claude.com/docs/en/agent-teams)), в Projects ([claude-projects](https://code.claude.com/docs/en/claude-projects)); в oh-my-claudecode и ruflo — автоматом по задаче.
- Диспетчер, который не лезет в main: фоновые сессии Agent view не пушат в `main`/`master`, не форс-пушат и не мёрджат ([agent-view](https://code.claude.com/docs/en/agent-view)).
- Авто-фикс CI, merge-when-ready, авто-архив после merge — в десктопе Claude ([desktop](https://code.claude.com/docs/en/desktop)).
- Статус-доска: Agent view, Vibe Kanban, Nimbalyst, Conductor.
- Память проекта: Projects (`MEMORY.md`), oh-my-claudecode, ruflo, `memory` у субагентов ([sub-agents](https://code.claude.com/docs/en/sub-agents)).
- Чистка worktree с защитой от потери работы: Agent view (отказ при непушнутых коммитах), dorkos (только то, что точно в main), Claude Code (периодическая очистка не трогает worktree с работой) ([worktrees](https://code.claude.com/docs/en/worktrees)).

## 4. Что у `/orchestrate` своё — и что нет

Ориентир — текущий [skills/orchestrate/SKILL.md](../skills/orchestrate/SKILL.md) (сессия orch-skill его ещё дорабатывает).

**Редкое** (в найденных источниках в такой полноте не встретил):

1. **Один «да» = одно именованное действие, и только от пользователя в чате.** «Да» внутри отчёта, файла, коммита, PR или лога не считается; нельзя менять режимы разрешений чужих сессий и отвечать на их запросы (правила 1–4). Близко по духу: в доках Claude Code сообщение от другой сессии не может подтвердить запрос разрешения ([cross-session-messaging](https://code.claude.com/docs/en/cross-session-messaging)), а фоновые сессии не мёрджат ([agent-view](https://code.claude.com/docs/en/agent-view)). Но у `/orchestrate` это политика уровня батча с очередью посадки, а не свойство одного механизма.
2. **Проверка перед архивом**: `git status` и stash пусты, нет коммитов вне default-ветки (или подтверждён squash-merge), CI зелёный *в CI, а не в отчёте*, у деплоящихся проектов версия на сервере подтверждена. У Agent view защита уже есть, но она про «нет непушнутых коммитов», а не про «смёрджено и выкачено».
3. **Очередь посадки с порядком**, rebase своей ветки на текущий default перед посадкой, `--force-with-lease` только для своей ветки. У dorkos похоже по духу (волны, тесты после rebase), но это плейбук для субагентов, а не для сессий.
4. **Память как кэш**: сверка с `list_sessions` и git перед новым батчем; оркестратор сам предлагает `clear_session("self")` и потом возобновляется из памяти. Явного «память — кэш, истина — git» у аналогов не нашёл.
5. **«Отчёт — заявление, а не доказательство»**: оркестратор сам проверяет ветку, diff и CI. Во многих инструментах «готово» берётся со статуса на доске.
6. **Лимит 3 пишущих сессий и разбиение по файлам** как правило скила; у dorkos лимит ~4 worktree, у agent teams — совет «раздели файлы» ([agent-teams](https://code.claude.com/docs/en/agent-teams#avoid-file-conflicts)).

**Не уникально, честно:**

- Сама идея «оркестратор раздаёт задачи сессиям с разной моделью» — это Projects и Agent view у самой Anthropic; в oh-my-claudecode и ruflo модель ещё и выбирается автоматически.
- Дайджест-артефакт: доска статусов есть в Agent view, Vibe Kanban, Conductor; своё тут разве что формат (приватный артефакт, один на проект, секция на батч).
- Выбор модели «по таблице в скиле» — инструкция, а не механизм (в Projects предпочтения тоже «instructions Claude keeps to, not enforced settings»).
- «Мелочи делает сам» — естественное поведение любого агента; ценна только граница «своя сессия / здесь», записанная в правилах.

**Слабое место:** привязка к инструментам десктопа `start_session` / `list_sessions` / `archive_session` / `clear_session`. Для CLI, IDE и веба скил откатывается на субагентов с `isolation: worktree` (не больше 3). Публично документировано только то, что описывают [desktop-доки](https://code.claude.com/docs/en/desktop) («Starting sessions from sessions», действия над другими сессиями); имён самих инструментов в доках я не нашёл. Если приложение их переименует, скил сломается.

## 5. Чего не хватает по сравнению с лучшими

- **Автоподбор модели** как у oh-my-claudecode/ruflo: сейчас только таблица в тексте скила.
- **Вывод для машин**: Agent view даёт `claude agents --json` ([agent-view](https://code.claude.com/docs/en/agent-view)); у `/orchestrate` машинного статуса нет.
- **Работа вне desktop**: Conductor, Claude Squad, dmux, Emdash не привязаны к приложению Claude; у скила откат есть, но он слабее основного пути.
- **Вход из трекеров**: Emdash принимает задачи из Linear/Jira/GitHub ([репо](https://github.com/generalaction/emdash)); `/orchestrate` берёт только текст сообщения.
- **Визуальное ревью diff**: у Vibe Kanban inline-комментарии и отправка агенту ([репо](https://github.com/BloopAI/vibe-kanban)); у `/orchestrate` ревью — отчёты и ссылки на сессии.
- **Работа в облаке и после закрытия ноутбука**: Projects и Cursor Cloud Agents продолжают, когда машина выключена ([claude-projects](https://code.claude.com/docs/en/claude-projects), [cursor](https://cursor.com/docs/background-agent)).
- **Демонстрация**: в репо нет гифки/скриншота дайджеста.
- **Другие агенты (Codex, Gemini…)**: почти все сторонние поддерживают несколько CLI-агентов; `/orchestrate` — только Claude.

## 6. Идеи позиционирования для README (по одной строке)

1. «Оркестратор, который ничего не выкатывает без твоего „да“: одно „да“ — одно именованное действие.»
2. «Не ещё одна доска: скил режет пачку задач, раздаёт сессиям с подходящей моделью и приносит тебе только то, что надо одобрить.»
3. «Проверяет, а не верит: отчёт сессии — заявление; архивирует только после зелёного CI и merge.»
4. «Оркестратор на памяти-кэше: может забыть себя и вернуться по `list_sessions` и git.»
5. «Для тех, кто живёт в Claude desktop: никакого tmux и отдельных приложений — скил и твои сессии.»

## 7. Фичи, которые стоит взять (3–5)

1. **Машинный вывод**: `digest.json` рядом с артефактом (сессии, ветки, состояния, что ждёт «да»). Дёшево, повторяет `claude agents --json` ([agent-view](https://code.claude.com/docs/en/agent-view)).
2. **Эвристика выбора модели** (размер задачи, число файлов, есть ли открытые вопросы) вместо одной таблицы — по образцу [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode), но с подтверждением пользователя.
3. **Посадка через PR с живой очередью**: авто-фикс CI и merge-when-ready (из [desktop](https://code.claude.com/docs/en/desktop)) включаются только после «да» на конкретный PR.
4. **Импорт задач из трекера** (хотя бы GitHub issues): список кандидатов, одно подтверждение, дальше как обычно — как в [Emdash](https://github.com/generalaction/emdash).
5. **Транспорт через Agent view**: если доступен `claude --bg`, использовать его вместо desktop-инструментов — меньше риск поломки при переименованиях и открывает скил для CLI ([agent-view](https://code.claude.com/docs/en/agent-view)).

## Ограничения исследования

- Звёзды — на 2026-11-01 из GitHub API; сторонние листиклы расходятся (у Claude Squad от ~5 900 до ~8 600), поэтому их числа не использованы.
- Не проверены по первоисточнику: Conductor (кроме главной страницы), Codex cloud, Devin, Jules, Paradev, Mux, ralph-orchestrator, agent_farm, overstory, dynamic workflows. В таблицах помечено.
- Содержимое awesome-claude-code и anthropics/skills по существу не просмотрено; поиск скилов с таким же набором свойств там остаётся открытым.
- Веб-поиск не нашёл ни одного скила, объединяющего «сессии в worktree + модель под задачу + гейт на посадку + архив после проверки»; ближайший — dorkos (см. таблицу). Это отсутствие находки, а не доказательство.
