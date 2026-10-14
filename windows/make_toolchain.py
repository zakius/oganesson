#!/usr/bin/env python3
"""Makes the Windows toolchain package that Chromium's cross build expects, from
MSVC and the Windows SDK as msvc-wine downloads them (vsdownload.py; its use
accepts Microsoft's license terms).

Usage: windows/make_toolchain.py MSVC_DIR SRC_TREE OUT_DIR

Chromium's own package is made on Windows (depot_tools'
win_toolchain/package_from_installed.py, from an installed Visual Studio). This
makes the same layout here: VC/, Windows Kits/10/ (with the SetEnv files the
build reads its environment from, and the Debugging Tools' DLLs), DIA SDK/,
the runtime DLLs in sys32/ and sys64/, and VS_VERSION. The zip lands in
OUT_DIR as <hash>.zip, under the hash depot_tools checks after unpacking it;
the build then takes it with
DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL=OUT_DIR and GYP_MSVS_HASH_<pin>=<hash>
(printed, and written to OUT_DIR/hash).
"""
import glob, hashlib, io, os, shutil, subprocess, sys, tempfile, urllib.request, zipfile
from pathlib import Path

VS_VERSION = '2026'
# The SDK's Debugging Tools, which Chromium ships dbghelp.dll and dbgcore.dll
# from: Visual Studio's installer doesn't carry them, Microsoft's NuGet package
# does (under the Windows SDK's license).
DBGENG = ('https://www.nuget.org/api/v2/package/Microsoft.Debugging.Platform.DbgEng/'
          '20260319.1511.0')
DBGENG_SHA256 = '875678516f9ceed4a1c8b9b106d165106fcaa38723ad7c584c47b95b231600de'


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    msvc, tree, out = (Path(a).resolve() for a in sys.argv[1:])
    win_toolchain = tree / 'third_party/depot_tools/win_toolchain'
    sys.path.insert(0, str(win_toolchain))
    import get_toolchain_if_necessary as fetcher  # pylint: disable=import-outside-toplevel
    import package_from_installed as packager  # pylint: disable=import-outside-toplevel

    (vc_tools,) = glob.glob(str(msvc / 'VC/Tools/MSVC/14.*'))
    (sdk,) = [Path(p).name for p in glob.glob(str(msvc / 'Windows Kits/10/Include/10.*'))]
    (redist,) = glob.glob(str(msvc / 'VC/Redist/MSVC/14.*.*'))

    with tempfile.TemporaryDirectory(dir=out) as tmp:
        stage = Path(tmp, 'vs_files', 'stage')
        stage.mkdir(parents=True)
        for part in ('VC', 'Windows Kits', 'DIA SDK'):
            subprocess.run(['cp', '-a', '--reflink=auto', str(msvc / part), str(stage)], check=True)
        (stage / 'VS_VERSION').write_text(VS_VERSION)
        for cpu, sys_dir in (('x86', 'sys32'), ('x64', 'sys64')):
            (stage / sys_dir).mkdir()
            for dll in [*glob.glob(f'{redist}/{cpu}/Microsoft.VC*.CRT/*.dll'),
                        *glob.glob(str(msvc / f'Windows Kits/10/Redist/{sdk}/ucrt/DLLs/{cpu}/*.dll'))]:
                shutil.copy2(dll, stage / sys_dir)
        (stage / 'sysarm64').mkdir()
        with urllib.request.urlopen(DBGENG, timeout=60) as response:
            package = response.read()
        if hashlib.sha256(package).hexdigest() != DBGENG_SHA256:
            sys.exit('make_toolchain.py: the Debugging Tools package changed')
        with zipfile.ZipFile(io.BytesIO(package)) as nupkg:
            for arch, cpu in (('amd64', 'x64'), ('x86', 'x86'), ('arm64', 'arm64')):
                debuggers = stage / 'Windows Kits/10/Debuggers' / cpu
                debuggers.mkdir(parents=True)
                for dll in ('dbghelp.dll', 'dbgcore.dll'):
                    (debuggers / dll).write_bytes(nupkg.read(f'content/{arch}/{dll}'))

        # depot_tools' generator, with its globals as its main() sets them. It
        # names the files with Windows separators, which on Linux are part of
        # the name: moved to where they belong.
        packager._win_version = sdk  # pylint: disable=protected-access
        packager._vc_tools = os.path.relpath(vc_tools, msvc)  # pylint: disable=protected-access
        packager.GenerateSetEnvCmd(str(stage))
        for generated in stage.glob('Windows Kits\\10\\bin\\SetEnv*'):
            generated.rename(stage / 'Windows Kits/10/bin' / generated.name.split('\\')[-1])

        # The hash as depot_tools computes it after unpacking, relative to vs_files.
        os.chdir(Path(tmp))
        digest = fetcher.CalculateHash('vs_files', 'stage')[:10]
        zip_path = out / f'{digest}.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED, allowZip64=True) as zf:
            for path in fetcher.GetFileList(os.path.join('vs_files', 'stage')):
                zf.write(path, os.path.relpath(path, os.path.join('vs_files', 'stage')))
    (out / 'hash').write_text(digest + '\n')
    print(digest)


if __name__ == '__main__':
    main()
