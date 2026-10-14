#!/usr/bin/env bash
# The Windows test VM: Windows 11 LTSC (evaluation) in Docker (dockur/windows,
# KVM), with its files in work/win/vm (see docs/windows.md).
#
#   windows/vm/vm.sh start [ADDRESS]  create or start it; its screen (port 8006)
#                                     and RDP (3389) also on ADDRESS, e.g. this
#                                     machine's Tailscale address
#   windows/vm/vm.sh ssh [COMMAND]    PowerShell in it, as the oganesson user
#   windows/vm/vm.sh install          the packages' newest installer, run with its
#                                     GUI on the VM's desktop (gui-install.ps1)
#   windows/vm/vm.sh run              the installed browser on the VM's desktop
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
vm="$root/work/win/vm"
here="$root/windows/vm"

ssh_vm() {
    ssh -q -i "$vm/ssh_key" -p 2222 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        -o UserKnownHostsFile="$vm/known_hosts" oganesson@127.0.0.1 "$@"
}

case "${1:-}" in
start)
    if docker container inspect oganesson-win >/dev/null 2>&1; then
        docker start oganesson-win >/dev/null
        exit
    fi
    mkdir -p "$vm/storage" "$vm/oem" "$vm/share"
    # Windows Setup on btrfs: no copy-on-write for the disk image.
    chattr +C "$vm/storage" 2>/dev/null || true
    [ -f "$vm/ssh_key" ] || ssh-keygen -q -t ed25519 -N "" -C oganesson-win-vm -f "$vm/ssh_key"
    [ -f "$vm/password" ] || python3 -c 'import secrets; print(secrets.token_urlsafe(16))' \
        > "$vm/password"
    chmod 600 "$vm/password" "$vm/ssh_key"
    sed "s|KEY|$(cat "$vm/ssh_key.pub")|" "$here/install.bat" > "$vm/oem/install.bat"
    ports=(-p 127.0.0.1:8006:8006 -p 127.0.0.1:2222:22)
    if [ -n "${2:-}" ]; then
        ports+=(-p "$2:8006:8006" -p "$2:3389:3389" -p "$2:3389:3389/udp")
    fi
    docker run -d --name oganesson-win --restart unless-stopped "${ports[@]}" \
        --device=/dev/kvm --device=/dev/net/tun --cap-add NET_ADMIN --stop-timeout 120 \
        -e VERSION=11l -e RAM_SIZE=8G -e CPU_CORES=8 -e DISK_SIZE=80G \
        -e USERNAME=oganesson -e PASSWORD="$(cat "$vm/password")" \
        -v "$vm/storage:/storage" -v "$vm/oem:/oem" -v "$vm/share:/shared" dockurr/windows
    echo "Installing Windows; watch it at http://localhost:8006. SSH works once it's done."
    ;;
ssh)
    shift
    ssh_vm "$@"
    ;;
install)
    installer="$(ls -t "$root"/work/dl/windows/*/*-installer.exe | head -1)"
    cp "$installer" "$vm/share/oganesson-installer.exe"
    cp "$here/gui-install.ps1" "$vm/share/"
    ssh_vm 'powershell -NoProfile -ExecutionPolicy Bypass -File \\host.lan\Data\gui-install.ps1'
    echo "The installer is on the VM's desktop: http://localhost:8006"
    ;;
run)
    cp "$here/run-oganesson.ps1" "$vm/share/"
    ssh_vm 'powershell -NoProfile -ExecutionPolicy Bypass -File \\host.lan\Data\run-oganesson.ps1'
    ;;
*)
    sed -n '2,13s/^# \{0,1\}//p' "$0"
    exit 2
    ;;
esac
