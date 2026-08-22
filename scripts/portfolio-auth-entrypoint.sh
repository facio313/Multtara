#!/bin/sh
set -eu

fail() {
  printf '%s\n' "portfolio auth entrypoint: $*" >&2
  exit 1
}

build_contract_file=/etc/portfolio-auth-build
[ -f "$build_contract_file" ] || fail 'image build contract is missing'
[ ! -L "$build_contract_file" ] || fail 'image build contract must not be a symlink'
[ "$(stat -c '%a' "$build_contract_file")" = 444 ] || \
  fail 'image build contract must have mode 0444'
[ "$(awk 'END { print NR }' "$build_contract_file")" -eq 2 ] || \
  fail 'image build contract must contain exactly two lines'

build_contract=$(cat "$build_contract_file")
runtime_contract=$(/usr/local/bin/portfolio-auth-mode.sh contract)
[ "$runtime_contract" = "$build_contract" ] || \
  fail 'runtime branch/auth mode conflicts with the image build'

[ "$#" -gt 0 ] || fail 'a server command is required'
exec "$@"
