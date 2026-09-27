# acme-web

Storefront for Acme's hand-tool shop (fictional sample project for the Vepol demo).

- `src/cart.ts` — cart totals as shown to the shopper (amounts come from billing-api).
- `src/checkout.ts` — the checkout v2 submit flow.
- `src/flags.ts` — reads `config/flags.json`.

```sh
npm install
npm run dev     # http://localhost:3000
npm test
```
