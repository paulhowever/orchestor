# Где выложить orchestrate

Проверено 2026-11-01. Правила каталогов меняются, перед подачей открой ссылку на правила ещё раз.

Состояние репо на эту дату: создан 2026-11-01, MIT, 2 звезды. Плагин-манифест (`.claude-plugin/`) готов локально в 0.2.0, но ещё не запушен: пока его нет на GitHub, `/plugin marketplace add paulhowever/orchestor` не сработает.

## Сводка

| Каталог | Как попасть | Подходим? | Кто подаёт |
|---|---|---|---|
| Свой маркетплейс (`.claude-plugin/marketplace.json`) | Файл в репо, без заявки | **Да**, после пуша 0.2.0 | — |
| [Anthropic directory](https://claude.ai/directory) | Портал claude.ai/directory/manage | **Да, технически** | Павел, в браузере (нужен платный план) |
| [skills.sh](https://skills.sh) (`npx skills`) | Автоматически, по телеметрии установок | **Да**, после первых установок | Никто |
| [claude-plugins.dev](https://claude-plugins.dev) | Автоматическая индексация GitHub | **Да** (не проверено, что уже проиндексирован) | Никто |
| [claudemarketplaces.com](https://claudemarketplaces.com/submit) | Форма, вход через GitHub | **Скорее да** | Павел |
| [jeremylongshore/claude-code-plugins-plus-skills](https://github.com/jeremylongshore/claude-code-plugins-plus-skills) | Issue + PR в `sources.yaml` | **Можно**, но много бумаг | Павел |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | Только веб-форма issue | **Пока нет**: репо младше 14 дней | Только Павел руками, не Claude |
| [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) | PR | **Пока нет**: «только что созданные» не берут | Павел |
| [travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills) | PR | **Пока нет**: нужно ≥10 звёзд, PR не от ИИ | Павел руками |
| [wshobson/agents](https://github.com/wshobson/agents) | Issue, потом PR | **Нет** | — |
| [anthropics/skills](https://github.com/anthropics/skills) | Сторонние не принимают | **Нет** | — |
| `claude-plugins-official` | Только через партнёрский контакт в Anthropic | **Нет** | — |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | PR | **Нет**: почти не мёржат, просят переносимость | — |

Порядок: запушить 0.2.0 → Anthropic directory и claudemarketplaces.com → примерно с 15 ноября, при свежих коммитах, awesome-claude-code → VoltAgent и travisvn, когда наберутся звёзды и живые установки.

## Тексты, общие для всех заявок

**Название:** orchestrate (репо `paulhowever/orchestor`)

**Одна строка (≤10 слов):** Splits a batch into Claude sessions; lands nothing without approval.

**Коротко (1–3 предложения, без рекламы, без обращения к читателю):**
> A Claude Code skill, packaged as a plugin, that splits one message holding several tasks into separate Claude desktop sessions, each with its own worktree, branch and a model chosen for the task. It checks each session's report against git and CI before calling it done, lands branches one at a time, and pushes, merges, deploys or releases only after the user's explicit yes naming that action. Finished sessions are archived only when their worktrees are clean and their commits are merged.

**Ограничение (писать честно везде):** full mode needs the Claude desktop app (Code tab) session tools; in the CLI it falls back to worktree subagents.

**Установка:** `claude plugin install orchestrate --marketplace paulhowever/orchestor`

## 1. Свой маркетплейс

- Правила: https://code.claude.com/docs/en/plugins/publish#publish-through-your-own-marketplace, https://code.claude.com/docs/en/plugins/marketplace-reference
- Сделано: `.claude-plugin/plugin.json` (имя `orchestrate`, версия 0.2.0) и `.claude-plugin/marketplace.json` (маркетплейс `orchestor`, плагин с `"source": "./"`). `claude plugin validate --strict .` проходит. Установка из локальной папки во временный `CLAUDE_CONFIG_DIR` прошла: `orchestrate@orchestor`, 1 скил.
- Осталось: пуш в main. После пуша проверить `claude plugin install orchestrate --marketplace paulhowever/orchestor` на чистом конфиге.
- Версии: в `plugin.json` стоит `version`, поэтому **каждый релиз — поднимать версию**, иначе `claude plugin update` скажет «already at the latest version».

## 2. Anthropic directory (claude.ai/directory)

- Правила: https://code.claude.com/docs/en/plugins/publish#submit-to-anthropics-directory, чек-лист https://claude.com/docs/plugins/pre-submission-checklist, подача https://claude.com/docs/plugins/submit
- Как: портал https://claude.ai/directory/manage. Нужен платный план claude.ai (Pro/Max/Ultra — со своего аккаунта), GitHub подключён к claude.ai с правом push в репо. Одобренные плагины зеркалятся в `anthropics/claude-plugins-community` (`@claude-community`), PR туда закрываются автоматически.
- Блокируют подачу: нет `.claude-plugin/plugin.json`, README короче 40 слов, нет LICENSE или поля `license`, файлы `.DS_Store`, занятое или зарезервированное имя. Одна заявка — один плагин. Дальше автоматический скан и, возможно, ручной ревью. Ограничений по возрасту и звёздам нет.
- Подходим: да, всё перечисленное есть. Риски: имя `orchestrate` общее, может оказаться занятым (не проверено). На claude.ai и в Cowork инструментов сессий нет, так что полезен листинг в основном в Claude Code — это надо написать в описании.
- Кто: только Павел, в браузере.
- Текст для поля описания:
  > Splits one message with several tasks into separate Claude Code sessions in the Claude desktop app (own worktree and branch each, a model per task), checks their reports against git and CI, and lands work only after your explicit yes naming that action. Works fully in Claude Code in the desktop app's Code tab; in the CLI it falls back to worktree subagents. On claude.ai and in Cowork the session tools are not available.

## 3. skills.sh / `npx skills`

- Правила: https://github.com/vercel-labs/skills/blob/main/docs/creating-skills.md, https://github.com/vercel-labs/skills/blob/main/docs/troubleshooting.md
- Как: заявки нет. Скил появляется в каталоге, когда кто-то ставит его через `npx skills add paulhowever/orchestor` (анонимная телеметрия, только публичные GitHub-репо). CLI находит `skills/*/SKILL.md` и читает `.claude-plugin/marketplace.json`, так что раскладка уже подходит.
- Безопасность: Vercel прогоняет скилы через автоматический аудит (Gen, Socket, Snyk), помеченные как вредоносные скрываются — https://vercel.com/changelog/automated-security-audits-now-available-for-skills-sh. Исследование Snyk «ToxicSkills» (февраль 2026) нашло вредоносные нагрузки в десятках скилов ClawHub и skills.sh — https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/. Поэтому в README основной путь — плагин или ручной клон, а `npx skills` можно упомянуть как вариант для тех, кто им и так пользуется.
- Делать ничего не нужно. Сами `npx skills` не запускали.

## 4. hesreallyhim/awesome-claude-code

- Правила: https://github.com/hesreallyhim/awesome-claude-code/blob/main/CONTRIBUTING.md
- Форма: https://github.com/hesreallyhim/awesome-claude-code/issues/new?template=recommend-resource.yml
- Как: **только веб-форма issue**. Через `gh` нельзя, PR не принимают; за нарушение могут временно ограничить доступ к репо. Ресурс может быть написан агентом, но рекомендацию должен подавать человек. По одной рекомендации за раз. Бот проверяет форму и закрывает то, что не проходит.
- Требования: репо старше 14 дней и с признаками активной разработки — или от 100 звёзд. Описание 1–3 предложения, без рекламы, без обращения к читателю, без эмодзи. В чек-листе есть «смотрел репо своими глазами» и ловушка, которую надо оставить пустой.
- Подходим: **пока нет**. Самое раннее — около 2026-11-15, и нужны коммиты после первого дня.
- Категория: **Agent Orchestration** (запасной вариант — Skills).
- Текст для формы (Павел вставляет сам):
  - Name: `orchestrate`
  - URL: `https://github.com/paulhowever/orchestor`
  - Description: текст «Коротко» из начала этого файла.

## 5. VoltAgent/awesome-agent-skills

- Правила: https://github.com/VoltAgent/awesome-agent-skills/blob/main/CONTRIBUTING.md
- Как: PR с заголовком `Add skill: paulhowever/orchestrate`, описание ≤10 слов, имя с префиксом автора.
- Подходим: **пока нет**: «brand new skills that were just created are not accepted». Вернуться, когда будут живые установки и звёзды.
- Строка для PR: `- **[paulhowever/orchestrate](https://github.com/paulhowever/orchestor)** - Splits a batch into Claude sessions; lands nothing without approval.`

## 6. travisvn/awesome-claude-skills

- Правила: https://github.com/travisvn/awesome-claude-skills/blob/main/CONTRIBUTING.md
- Как: PR. Без 10 звёзд закрывается автоматически. PR не должен быть сгенерирован или подан с помощью ИИ — значит, только руками Павла. Предпочитают скилы больше одного `SKILL.md`. Список выглядит полузаброшенным (последний пуш — апрель 2026).
- Подходим: **пока нет**.

## 7. jeremylongshore/claude-code-plugins-plus-skills (tonsofskills.com)

- Правила: https://github.com/jeremylongshore/claude-code-plugins-plus-skills/blob/main/.github/CONTRIBUTING.md
- Как: сначала issue по шаблону `plugin-submission.yml`, потом либо PR с плагином, либо «Path B» — PR с записью в `sources.yaml` (зеркало раз в неделю, источник правды остаётся наш репо). Нужны README, LICENSE, валидный plugin.json; проходят рубрику на 100 баллов и бот-прескрин; без зеркала требуют `PRD.md`. Ожидают пометку об участии ИИ.
- Подходим: **можно через Path B**, ограничений по звёздам не нашли. Много бумаги за небольшой охват — по желанию.

## 8. claudemarketplaces.com и claude-plugins.dev

- claudemarketplaces.com: https://claudemarketplaces.com/submit — вход через GitHub, подать репо маркетплейса. Бесплатно (есть платный приоритет за $4 — не нужен). Требований не опубликовано. Подходим, скорее всего.
- claude-plugins.dev: https://github.com/Kamalnrf/claude-plugins — сам индексирует публичные плагины и скилы на GitHub. Делать ничего не нужно; после пуша проверить, что появились.

## 9. Куда не идём

- **anthropics/skills**: только скилы Anthropic; сторонние PR закрывают, партнёрские скилы Anthropic выбирает сама.
- **claude-plugins-official**: в портал не входит, только через партнёрский контакт.
- **wshobson/agents**: от внешних плагинов ждут «demonstrably maintained project with real adoption (not a v0.x repo created weeks ago)» и переносимость на 7 инструментов; нам нужны инструменты сессий десктопа.
- **ComposioHQ/awesome-claude-skills**: за последние 30 закрытых PR ни одного мёржа, просят работу на всех платформах Claude.

## Не проверено

- Занято ли имя `orchestrate` в Anthropic directory.
- Редиректит ли старая форма https://clau.de/plugin-directory-submission на новый портал.
- Реальные критерии claudemarketplaces.com.
- Есть ли orchestrate уже в skills.sh или claude-plugins.dev.
