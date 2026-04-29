#!/usr/bin/env bash
input=$(cat)

user=$(whoami)
host=$(hostname -s)
dir=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // empty')
[ -z "$dir" ] && dir=$(pwd)
dir_short=$(basename "$dir")

model=$(echo "$input" | jq -r '.model.display_name // empty')

used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
if [ -n "$used" ]; then
  ctx_part=" | ctx:$(printf '%.0f' "$used")%"
else
  ctx_part=""
fi

five=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
week=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
limits_part=""
[ -n "$five" ] && limits_part=" | 5h:$(printf '%.0f' "$five")%"
[ -n "$week" ] && limits_part="$limits_part 7d:$(printf '%.0f' "$week")%"

model_part=""
[ -n "$model" ] && model_part=" | $model"

printf "%s@%s:%s%s%s%s" "$user" "$host" "$dir_short" "$model_part" "$ctx_part" "$limits_part"
