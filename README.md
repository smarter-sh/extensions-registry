# Smarter Extension Registry

The registry of [Smarter Extensions](https://docs.smarter.sh/en/latest/smarter-framework/smarter-extensions.html):
installable Python packages that add tools to the LLMs of a Smarter platform. Smarter platforms read
the signed index that this repository publishes, to show administrators the extensions they can
install, their publishers' trust badges, and the updates of the extensions they have installed.

## Publishing a release

1. Release your extension: bump its version, build its archive (`python manage.py package_extension`,
   or your repository's release workflow), and attach the archive to a GitHub release.
2. Open a pull request that adds one file, `extensions/<slug>/<version>.yaml`:

   ```yaml
   slug: weather
   version: 1.0.0
   publisher: smarter-sh
   archive_url: https://github.com/smarter-sh/smarter-extension-weather/releases/download/v1.0.0/weather-1.0.0.zip
   sha256: <the archive's hex sha256>
   ```

3. The first time you publish, add yourself to `publishers.yaml`, with `badge: community`.

CI downloads the archive, checks its sha256, and checks that its `pyproject.toml` has the same slug
and version. Once the pull request is merged, the index is rebuilt, signed and published, and
platforms that have the extension installed are offered the update within a day.

Rules:

- A released version is never changed. To fix one, release another.
- A slug belongs to the publisher that first published it.
- Only the Smarter team changes badges, keys, scripts and workflows (see `.github/CODEOWNERS`).

## Trust badges

| Badge | Who |
| --- | --- |
| `official` | The Smarter team |
| `verified` | Publishers that the Smarter team has vetted. Ask in an issue. |
| `community` | Everyone else |

## The index

CI publishes `index.json`, which `schema/index.schema.json` describes, and `index.json.sig`, the
base64 Ed25519 signature of its exact bytes, to GitHub Pages. Platforms verify the signature with the
public key in `keys/registry.pub`, which they are configured with as
`SMARTER_EXTENSION_REGISTRY_PUBLIC_KEY`. The private key is the `REGISTRY_SIGNING_KEY` secret.
