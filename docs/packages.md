# Package repository

`linux/publish-repo.sh` publishes signed apt and dnf repositories with the 3 newest release builds, for x86-64-v2 machines. Below, `<domain>` is the repository's domain.

## Server setup

The server needs Docker, a Traefik that routes containers by their labels on a `websecure` entry point, and a DNS record for `<domain>`. Packages exceed Cloudflare's proxy file size limits, so the record must not be proxied.

On the build machine:

1. Make the signing key:
   ```sh
   export GNUPGHOME=~/.local/share/oganesson-repo/gnupg
   mkdir -p -m 700 "$GNUPGHOME"
   gpg --batch --pinentry-mode loopback --passphrase '' \
       --quick-gen-key 'oganesson packages' rsa4096 sign never
   ```
2. Write `~/.local/share/oganesson-repo/repo.env`:
   ```sh
   REPO_DOMAIN=<domain>
   REPO_TARGET=<ssh host>:pkgrepo
   ```

Back up `~/.local/share/oganesson-repo`. The key exists only there; with a new key, every machine must import it again.

## Publishing

1. `./oganesson.py build --release`
2. `linux/pack.sh`
3. `linux/publish-repo.sh`

`pack.sh` also keeps the tarball the packages are made from. `publish-repo.sh` uploads only that tarball and the local .deb's `Depends:` line to `REPO_TARGET`. There, `linux/package/repo-build.sh` makes the .deb and .rpm natively, also on arm64. debbuild can't run `ldd` on x86 binaries there, so it takes the uploaded `Depends:` line instead. The repository metadata comes back to the build machine to be signed. `publish-repo.sh` also starts the server's compose project (`linux/package/repo-compose.yaml`), which serves the repository.

## Adding the repository

Debian, Ubuntu, PikaOS:

```sh
curl -fsSL https://<domain>/oganesson.asc | sudo gpg --dearmor -o /usr/share/keyrings/oganesson.gpg
echo 'deb [signed-by=/usr/share/keyrings/oganesson.gpg] https://<domain>/deb ./' | sudo tee /etc/apt/sources.list.d/oganesson.list
sudo apt update && sudo apt install oganesson
```

Fedora:

```sh
sudo curl -fsSL -o /etc/yum.repos.d/oganesson.repo https://<domain>/oganesson.repo
sudo dnf install oganesson
```

The dnf repository checks the signature on its metadata, which holds each package's checksum. The packages themselves are not signed, so the repository file sets `gpgcheck=0`.

New builds then arrive with the system's updates: Discover, GNOME Software, `apt upgrade` or `dnf upgrade`. To install them without asking, turn on automatic updates in Discover or GNOME Software, or use `unattended-upgrades` with the origin `oganesson` or `dnf5-automatic`.

## After an upgrade

A running browser keeps the old version until it restarts, and new helper processes would read the new version's files. Within seconds of an upgrade, the app menu button shows "Update", and "Relaunch to update" in the app menu restarts the browser with its windows, tabs and back history (`patches/oganesson/core/update-prompt.patch`). Chromium's update poller watches the install folder (`enable_update_notifications` in `linux/flags.gn`). The patch makes it count a new file at the binary's path as an update, because a rebuild on the same Chromium version doesn't change the version the binary reports. `tools/e2e/test_update_prompt.py` covers it.
