# {{PROJECT_NAME}} — log

Format:

```
## [YYYY-MM-DD] <op> | <description>
```

Operations: `ingest`, `query`, `experiment`, `lint`, `decision`, `milestone`.

Quick view:
```
grep "^## \[" wiki/log.md | tail -20
```

---

## [{{DATE}}] milestone | Wiki created via `new-wiki`
