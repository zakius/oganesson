#!/usr/bin/env bash
# Builds dubna/rust/oganesson_sync (Firefox Sync over application-services) into
# OUT/oganesson_sync.dll, with the NSS DLLs it loads next to it, inside the
# Windows build container after the browser (windows/container-build.sh).
# Chromium's nightly rustc and cargo build the standard library for Windows
# themselves (-Zbuild-std, from the toolchain's rust-src); Chromium's clang-cl
# and lld-link compile and link against MSVC and the SDK (/winsysroot, the
# toolchain package build/vs_toolchain.py mounted). NSS is MSYS2's UCRT64 build,
# pinned below; its MinGW import libraries serve lld-link as they are.
set -euo pipefail
src="$(realpath "$1")"  # the Chromium tree
out="$2"                # the browser's output folder
crate=/oganesson/dubna/rust/oganesson_sync
target="$out/oganesson_sync"
cache=/work/win/msys2

# MSYS2's NSS and what it loads (NSPR, and SQLite for softokn3). Its DLLs import
# nothing else but Windows'.
msys2=https://repo.msys2.org/mingw/ucrt64
packages=(
    "mingw-w64-ucrt-x86_64-nss-3.131-1-any.pkg.tar.zst 01da502b6ccc9ce4dfbd251baa6532328a21aedbf22328f208e76327653047c4"
    "mingw-w64-ucrt-x86_64-nspr-4.40-1-any.pkg.tar.zst 35f0f60025cb0d20039f3d2c59df744a9308fe264c4606d49685e87efce5984a"
    "mingw-w64-ucrt-x86_64-sqlite3-3.54.0-1-any.pkg.tar.zst fc7100490316733bbb96d5633d305a5d6c579200c321969cfa21d5a128055e65"
)
nss="$target/nss"
rm -rf "$nss"
mkdir -p "$cache" "$nss"
for entry in "${packages[@]}"; do
    read -r file sha <<< "$entry"
    [ -f "$cache/$file" ] || curl -sfL -o "$cache/$file" "$msys2/$file"
    echo "$sha  $cache/$file" | sha256sum -c --quiet
    zstd -dc "$cache/$file" | tar -xf - -C "$nss" ucrt64
done
ucrt64="$nss/ucrt64"
# nss_sys links these by their Windows names; nssckbi and c++ resolve to
# nothing it uses, an empty archive.
mkdir -p "$nss/lib"
for pair in nss3:libnss3 nssutil3:libnssutil3 softokn3:libsoftokn3 freebl3:libfreebl \
        nspr4:libnspr4 plc4:libplc4 plds4:libplds4; do
    cp "$ucrt64/lib/${pair#*:}.dll.a" "$nss/lib/${pair%%:*}.lib"
done
llvm="$src/third_party/llvm-build/Release+Asserts/bin"
for lib in nssckbi c++; do
    rm -f "$nss/lib/$lib.lib"
    "$llvm/llvm-ar" rc "$nss/lib/$lib.lib"
done

winsysroot="$src/third_party/depot_tools/win_toolchain/vs_files/$(cat /work/win/toolchain/hash)"
mkdir -p "$src/../cargo-home"
export CARGO_HOME="$(realpath "$src/../cargo-home")"
export CARGO_TARGET_DIR="$target"
export RUSTC="$src/third_party/rust-toolchain/bin/rustc"
export NSS_DIR="$nss"
export CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER="$llvm/lld-link"
export RUSTFLAGS="-C link-arg=/winsysroot:$winsysroot"
# C code in crates (SQLite, bundled by rusqlite for interrupt-support).
export CC_x86_64_pc_windows_msvc="$llvm/clang-cl"
export CFLAGS_x86_64_pc_windows_msvc="/winsysroot $winsysroot"
export AR_x86_64_pc_windows_msvc="$llvm/llvm-ar"
"$src/third_party/rust-toolchain/bin/cargo" build --release --locked \
    --target x86_64-pc-windows-msvc -Zbuild-std=std,panic_unwind \
    --manifest-path "$crate/Cargo.toml"
cp "$target/x86_64-pc-windows-msvc/release/oganesson_sync.dll" "$out/"
for dll in nss3 nssutil3 softokn3 freebl3 libnspr4 libplc4 libplds4 libsqlite3-0; do
    cp "$ucrt64/bin/$dll.dll" "$out/"
done
