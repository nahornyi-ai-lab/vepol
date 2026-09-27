# design-system

Design tokens and components shared by acme-web and the billing admin pages
(fictional sample project for the Vepol demo).

- `tokens/colors.json` — colour tokens, the single source for web and email.
- `src/tokens.ts` — typed access to the tokens.
- `src/Button.tsx` — the button used across checkout and admin.

```sh
npm run build       # writes dist/tokens.css and dist/tokens.email.json
npm run contrast    # fails on any text/background pair under WCAG AA
```
