#!/usr/bin/env bash
set -euo pipefail

project_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

timeout_command=()
if command -v timeout >/dev/null 2>&1; then
	timeout_command=(timeout 300)
elif command -v gtimeout >/dev/null 2>&1; then
	timeout_command=(gtimeout 300)
fi

godot --headless --path "$project_directory" --import
godot --headless --path "$project_directory" --script res://tests/run_tests.gd

shopt -s nullglob
for scene_path in "$project_directory"/tests/integration/*.tscn; do
	script_path="${scene_path%.tscn}.gd"
	if [[ -f "$script_path" ]] && grep -q "extends IntegrationTest" "$script_path"; then
		scene_name="$(basename "$scene_path")"
		"${timeout_command[@]+"${timeout_command[@]}"}" godot --headless --path "$project_directory" "res://tests/integration/$scene_name"
	fi
done
