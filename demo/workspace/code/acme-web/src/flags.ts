import flags from "../config/flags.json";

type Flag = { percent: number };

// A shopper is in a rollout when their stable bucket (0-99) is below the flag's percent.
export function isEnabled(name: keyof typeof flags, shopperId: string): boolean {
  const flag: Flag | undefined = (flags as Record<string, Flag>)[name];
  if (!flag) return false;
  return bucket(shopperId) < flag.percent;
}

function bucket(id: string): number {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return hash % 100;
}
