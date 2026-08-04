#!/bin/zsh
set -euo pipefail

readonly account="radspeed-mac-fracture-worker"
readonly access_service="radspeed-strong-worker-access-key"
readonly secret_service="radspeed-strong-worker-secret-key"
readonly keychain="${HOME}/Library/Keychains/login.keychain-db"

access_key="$(/bin/launchctl getenv AWS_ACCESS_KEY_ID)"
secret_key="$(/bin/launchctl getenv AWS_SECRET_ACCESS_KEY)"
trap 'unset access_key secret_key' EXIT

if [[ -z "$access_key" || -z "$secret_key" ]]; then
  print -u2 "The current login session does not contain the worker credential."
  exit 1
fi

if ! /usr/bin/security show-keychain-info "$keychain" >/dev/null 2>&1; then
  print "macOS needs one approval to make the credential reboot-safe."
  /usr/bin/security unlock-keychain "$keychain"
fi

/usr/bin/security add-generic-password -U \
  -a "$account" \
  -s "$access_service" \
  -l "RadSpeed Mac fracture worker access key" \
  -w "$access_key" \
  "$keychain" >/dev/null

/usr/bin/security add-generic-password -U \
  -a "$account" \
  -s "$secret_service" \
  -l "RadSpeed Mac fracture worker secret key" \
  -w "$secret_key" \
  "$keychain" >/dev/null

/usr/bin/security find-generic-password \
  -a "$account" -s "$access_service" -w "$keychain" >/dev/null
/usr/bin/security find-generic-password \
  -a "$account" -s "$secret_service" -w "$keychain" >/dev/null

print "RadSpeed worker credential saved securely in macOS Keychain."
