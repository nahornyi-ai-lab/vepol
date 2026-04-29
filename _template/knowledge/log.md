# {{PROJECT_NAME}} — лог

Формат:

```
## [YYYY-MM-DD] <op> | <описание>
```

Операции: `ingest`, `query`, `experiment`, `lint`, `decision`, `milestone`.

Быстрый просмотр:
```
grep "^## \[" wiki/log.md | tail -20
```

---

## [{{DATE}}] milestone | Вика заведена через `new-wiki`
