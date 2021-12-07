"""Tooling to prepare and build AppImages."""

import dataclasses
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Iterable, List, Tuple

import click
import dataclasses_json
from rules_python.python.runfiles import runfiles

APPIMAGE_TOOL = Path(runfiles.Create().Rlocation("rules_appimage/appimage/private/tool/appimagetool.bin"))


@dataclasses.dataclass
class FileMapEntry(dataclasses_json.DataClassJsonMixin):
    dst: str
    src: str


@dataclasses.dataclass
class SymlinksEntry(dataclasses_json.DataClassJsonMixin):
    linkname: str
    target: str


@dataclasses.dataclass
class Manifest(dataclasses_json.DataClassJsonMixin):
    empty_files: List[str]
    files: List[FileMapEntry]
    symlinks: List[SymlinksEntry]


def make_appimage(
    manifest: Path,
    workdir: Path,
    entrypoint: Path,
    icon: Path,
    extra_args: Iterable[str],
    output_file: Path,
    quiet: bool,
) -> int:
    """Make an AppImage.

    See cli() for args.

    Returns:
        appimagetool return code
    """
    manifest_data = Manifest.from_json(manifest.read_text())
    with tempfile.TemporaryDirectory() as tmpdir_name:
        tmpdir = Path(tmpdir_name)
        appdir = tmpdir / "AppDir"

        for empty_file in manifest_data.empty_files:
            (tmpdir / empty_file).parent.mkdir(parents=True, exist_ok=True)
            (tmpdir / empty_file).touch()
        for file in manifest_data.files:
            src = Path(file.src).resolve()
            dst = (tmpdir / file.dst).resolve()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src=src, dst=dst, follow_symlinks=True)
        for link in manifest_data.symlinks:
            linkfile = (tmpdir / link.linkname).resolve()
            linkfile.parent.mkdir(parents=True, exist_ok=True)
            linkfile.symlink_to(link.target)

        apprun_path = appdir / "AppRun"
        apprun_path.write_text(
            textwrap.dedent(
                f"""\
                #!/bin/sh
                set -eu
                HERE="$(dirname $0)"
                cd "${{HERE}}/{workdir.relative_to("AppDir")}"
                exec "{entrypoint.relative_to("AppDir")}" "$@"
                """
            )
        )
        apprun_path.chmod(0o751)

        apprun_path.with_suffix(".desktop").write_text(
            textwrap.dedent(
                """\
                [Desktop Entry]
                Type=Application
                Name=AppRun
                Exec=AppRun
                Icon=AppRun
                Categories=Development;
                Terminal=true
                """
            )
        )

        shutil.copy(src=icon, dst=appdir / f"AppRun{icon.suffix}", follow_symlinks=True)

        cmd = [
            os.fspath(APPIMAGE_TOOL),
            *extra_args,
            os.fspath(appdir),
            os.fspath(output_file),
        ]
        proc = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if not quiet or proc.returncode:
            print(proc.stdout)
        return proc.returncode


@click.command()
@click.option(
    "--manifest",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to manifest json with file and link defintions, e.g. 'bazel-out/k8-fastbuild/bin/tests/appimage_py-manifest.json'",
)
@click.option(
    "--workdir",
    required=True,
    type=click.Path(path_type=Path),
    help="Path to working dir, e.g. 'AppDir/tests/test_py.runfiles/rules_appimage'",
)
@click.option(
    "--entrypoint",
    required=True,
    type=click.Path(path_type=Path),
    help="Path to entrypoint, e.g. 'AppDir/tests/test_py'",
)
@click.option(
    "--icon",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Icon to use in the AppImage, e.g. 'external/AppImageKit/resources/appimagetool.png'",
)
@click.option(
    "--extra_arg",
    "extra_args",
    required=False,
    multiple=True,
    help="Any extra arg to pass to appimagetool, e.g. '--no-appstream'. Can be used multiple times.",
)
@click.option(
    "--quiet",
    is_flag=True,
    show_default=True,
    help="Don't print appimagetool output unless there is an error",
)
@click.argument(
    "output",
    type=click.Path(path_type=Path),
)
def cli(
    manifest: Path,
    workdir: Path,
    entrypoint: Path,
    icon: Path,
    extra_args: Tuple[str],
    quiet: bool,
    output: Path,
) -> None:
    """Tool for rules_appimage.

    Writes the built AppImage to OUTPUT.
    """
    sys.exit(make_appimage(manifest, workdir, entrypoint, icon, extra_args, output, quiet))


if __name__ == "__main__":
    cli()