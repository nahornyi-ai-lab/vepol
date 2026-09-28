import type { ButtonHTMLAttributes } from "react";
import { color } from "./tokens";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "danger" };

export function Button({ tone = "primary", style, ...rest }: Props) {
  return (
    <button
      {...rest}
      className="ds-button"
      style={{
        background: color(tone === "danger" ? "action.danger" : "action.primary"),
        color: color("text.inverse"),
        outlineColor: color("focus.ring"),
        ...style,
      }}
    />
  );
}
