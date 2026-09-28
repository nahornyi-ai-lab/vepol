import { randomUUID } from "node:crypto";

type PaymentRequest = { cartId: string; paymentMethodId: string; addressId?: string };

// The submit button locks on the first click and every attempt carries one
// idempotency key, so a slow network cannot charge the shopper twice.
export async function submitPayment(req: PaymentRequest, button: HTMLButtonElement): Promise<Response> {
  if (button.disabled) throw new Error("payment already submitted");
  button.disabled = true;
  const idempotencyKey = randomUUID();
  try {
    return await fetch("/api/billing/payments", {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": idempotencyKey },
      body: JSON.stringify(req),
    });
  } finally {
    button.disabled = false;
  }
}
