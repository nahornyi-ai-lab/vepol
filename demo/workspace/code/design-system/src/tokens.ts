import colors from "../tokens/colors.json";

export type ColorToken = `${keyof typeof colors.color}.${string}`;

// Look up "action.primary" style paths; unknown tokens fail loudly at build time.
export function color(path: ColorToken): string {
  const [group, name] = path.split(".");
  const value = (colors.color as Record<string, Record<string, string>>)[group]?.[name];
  if (!value) throw new Error(`unknown colour token: ${path}`);
  return value;
}
