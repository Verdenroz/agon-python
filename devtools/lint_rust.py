import subprocess

from funlog import log_calls
from rich import get_console, reconfigure
from rich import print as rprint

# Rust crate paths.
MANIFEST_PATH = "crates/agon-core/Cargo.toml"

reconfigure(emoji=not get_console().options.legacy_windows)  # No emojis on legacy windows.


def main():
    """Run Rust linting checks and report errors.

    Returns:
        int: The number of errors encountered during linting
    """
    rprint()

    errcount = 0
    errcount += run(["cargo", "fmt", "--manifest-path", MANIFEST_PATH])
    errcount += run(
        [
            "cargo",
            "clippy",
            "--manifest-path",
            MANIFEST_PATH,
            "--all-targets",
            "--fix",
            "--allow-dirty",
            "--allow-staged",
            "--",
            "-D",
            "warnings",
        ]
    )

    rprint()

    if errcount != 0:
        rprint(f"[bold red]:x: Rust lint failed with {errcount} errors.[/bold red]")
    else:
        rprint("[bold green]:white_check_mark: Rust lint passed![/bold green]")
    rprint()

    return errcount


@log_calls(level="warning", show_timing_only=True)
def run(cmd: list[str]) -> int:
    """Execute a command and handle its output.

    Args:
        cmd: The command to run as a list of strings

    Returns:
        int: 0 if the command succeeded, 1 if it failed
    """
    rprint()
    rprint(f"[bold green]>> {' '.join(cmd)}[/bold green]")
    errcount = 0
    try:
        subprocess.run(cmd, text=True, check=True)
    except subprocess.CalledProcessError as e:
        rprint(f"[bold red]Error: {e}[/bold red]")
        errcount = 1

    return errcount


if __name__ == "__main__":
    exit(main())
