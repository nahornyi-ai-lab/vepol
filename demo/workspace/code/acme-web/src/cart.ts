export type CartLine = { sku: string; name: string; quantity: number; unitCents: number };

// Display only: the amount charged is always the quote returned by billing-api.
export function subtotalCents(lines: CartLine[]): number {
  return lines.reduce((sum, line) => sum + line.quantity * line.unitCents, 0);
}

export function formatCents(cents: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(cents / 100);
}
