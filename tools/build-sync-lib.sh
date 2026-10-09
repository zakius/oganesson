#!/usr/bin/env bash
# Builds rust/oganesson_sync (Firefox Sync over application-services) into
# out/Default/liboganesson_sync.so, inside the build container. Uses
# Chromium's own rustc and cargo, links with its clang and the Debian sysroot
# against the system NSS Chromium already uses. Crates are pinned by
# Cargo.lock and cached in build/cargo-home.
set -euo pipefail

# Canonical paths: askama (uniffi) resolves templates relative to them.
src="$(realpath "$1")"   # the Chromium tree
mode="${2:-build}"       # or "test": build the unit tests, print their path
out="${3:-$src/out/Default}"  # the browser's output folder
level="${4:-}"           # an x86-64 level for release tiers, e.g. x86-64-v4
crate=/oganesson/rust/oganesson_sync
sysroot="$src/build/linux/debian_bullseye_amd64-sysroot"
syslib="$sysroot/usr/lib/x86_64-linux-gnu"
target="$out/oganesson_sync"

# nss_sys links NSS from NSS_DIR/lib. The sysroot has the libraries under
# their runtime names; the ones it lacks resolve to libnss3, whose soname is
# the only one recorded, and --as-needed drops what's unused.
nss="$target/nss"
mkdir -p "$nss/lib" "$nss/include"
for lib in nss3 nssutil3 nspr4 plc4 plds4; do
    ln -sf "$syslib/lib$lib.so" "$nss/lib/lib$lib.so"
done
for lib in freebl3 nssckbi softokn3; do
    ln -sf "$syslib/libnss3.so" "$nss/lib/lib$lib.so"
done
ln -sf "$syslib/libstdc++.so.6" "$nss/lib/libstdc++.so"

mkdir -p "$src/../cargo-home"
export CARGO_HOME="$(realpath "$src/../cargo-home")"
export CARGO_TARGET_DIR="$target"
export RUSTC="$src/third_party/rust-toolchain/bin/rustc"
export NSS_DIR="$nss"
clang="$src/third_party/llvm-build/Release+Asserts/bin/clang"
export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER="$clang"
# C code in crates (SQLite, bundled by rusqlite for interrupt-support).
export CC_x86_64_unknown_linux_gnu="$clang"
export CFLAGS_x86_64_unknown_linux_gnu="--sysroot=$sysroot"
export RUSTFLAGS="-C link-arg=--sysroot=$sysroot -C link-arg=-fuse-ld=lld -C link-arg=-Wl,-z,defs"
if [ -n "$level" ]; then
    RUSTFLAGS+=" -C target-cpu=$level"
    CFLAGS_x86_64_unknown_linux_gnu+=" -march=$level"
fi

cargo=("$src/third_party/rust-toolchain/bin/cargo")
if [ "$mode" = test ]; then
    "${cargo[@]}" test --release --locked --no-run --manifest-path "$crate/Cargo.toml" 2>&1 |
        sed -n 's/.*Executable unittests src\/lib.rs (\(.*\))/\1/p'
    exit
fi
"${cargo[@]}" build --release --locked --manifest-path "$crate/Cargo.toml"
cp "$target/release/liboganesson_sync.so" "$out/liboganesson_sync.so"
