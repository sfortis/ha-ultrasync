# Upstream Updates

This fork follows two upstream repositories:

- The integration comes from `caronc/ha-ultrasync`, branch `main`.
- The library comes from `caronc/ultrasync`, branch `master`. The fork of the library is `sfortis/ultrasync`, branch `panel-faults`, and a copy of it is vendored into `custom_components/ultrasync/vendor`.

Home Assistant installs this fork through HACS as a custom repository, so HACS no longer reports upstream releases. Check upstream manually about once a month. Turning on "Watch > Custom > Releases" for both upstream repositories on GitHub sends an e-mail on each release.

## Last Synchronisation

| Repository | Upstream version merged | Fork version | Date |
|---|---|---|---|
| `caronc/ha-ultrasync` | v1.3.0 | 1.6.0 | 2026-11-23 |
| `caronc/ultrasync` | v1.0.6 | 1.0.6+sfortis.1 | 2026-11-23 |

Update this table after every merge.

## Checking for New Commits

In a checkout of this repository, with the remote `upstream` pointing to `caronc/ha-ultrasync`:

```bash
git fetch upstream --tags
git log --oneline main..upstream/main
```

In a checkout of `sfortis/ultrasync`, with the remote `origin` pointing to `caronc/ultrasync`:

```bash
git fetch origin --tags
git log --oneline panel-faults..origin/master
```

An empty output means that nothing new has been released.

## Merging an Upstream Release

1. Merge the upstream release tag into `panel-faults` of the library and run its tests with `pytest`. Set `__version__` in `ultrasync/__init__.py` to the upstream version with a `+sfortis.N` suffix.
2. Run `scripts/vendor_ultrasync.sh <path to the ultrasync checkout>` in this repository and commit the copy.
3. Merge the upstream release tag of the integration into `main`.
4. Deploy to Home Assistant and check the log and the entities before releasing.
5. Raise `version` in `manifest.json`, push `main` and create a GitHub release with the tag `vX.Y.Z`. HACS offers only GitHub releases as updates.
6. Update the table above.

## Files That Conflict on Every Merge

- `manifest.json` must keep an empty `requirements` list, because the library is vendored. It keeps the fork's version and the fork's documentation and issue tracker URLs.
- `hacs.json` keeps the fork's minimum Home Assistant version (2026.8, needed for `via_device_id`).
- `config_flow.py` keeps `MINOR_VERSION = 2`, and the options flow must not define `__init__`, because `OptionsFlow.config_entry` is read-only in current Home Assistant.
- `__init__.py` stores the coordinator in `entry.runtime_data`, not in `hass.data`. Upstream code that uses `hass.data[DOMAIN]` has to be rewritten.
- `coordinator.py` also reads the panel event log, keeps zones and faults, and uses `hub_lock`. Apply upstream changes on top of the fork's version instead of taking upstream's file.

Upstream support for panic, fire and medical is limited to ComNav panels. Keep that limit, because these commands disarm an xGen8 panel.
