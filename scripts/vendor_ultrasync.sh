#!/usr/bin/env bash
# Copy the ultrasync library into the custom component.
#
# The integration ships its own copy of the library, so that Home Assistant
# does not install it from PyPI or GitHub on every start.  Run this script
# after changing the library, then commit the result.
#
# Usage: scripts/vendor_ultrasync.sh <path to an ultrasync checkout>
set -euo pipefail

src="${1:?usage: $0 <path to an ultrasync checkout>}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
dest="$repo/custom_components/ultrasync/vendor/ultrasync"

# The command line module needs click and is not used by the integration
modules=(__init__.py main.py common.py config.py logger.py)

rm -rf "$dest"
mkdir -p "$dest"
for m in "${modules[@]}"; do
    cp "$src/ultrasync/$m" "$dest/$m"
done
cp "$src/LICENSE" "$dest/LICENSE"

commit="$(git -C "$src" rev-parse HEAD)"
branch="$(git -C "$src" rev-parse --abbrev-ref HEAD)"
dirty=""
git -C "$src" diff --quiet HEAD -- ultrasync || dirty=" (with uncommitted changes)"
printf 'Vendored from https://github.com/sfortis/ultrasync\nBranch: %s\nCommit: %s%s\n' \
    "$branch" "$commit" "$dirty" > "$dest/SOURCE.txt"

echo "Copied ultrasync $branch@$commit$dirty to $dest"
