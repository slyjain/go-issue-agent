from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

def clone_repo(repo:str,workdir:Path,shallow:bool=True)->Path:
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.parent.mkdir(parents=True,exist_ok=True)
    url=f"https://github.com/{repo}.git"
    cmd=["git","clone"]
    if shallow:
        cmd+=["--depth",1]
    cmd+=[url,str(workdir)]
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    return workdir

def clone_repo_full(repo: str, workdir: Path) -> Path:
    return clone_repo(repo, workdir, shallow=False)


def checkout_commit(workdir: Path, sha: str) -> None:
    # Try direct checkout first (works on full clones)
    result = subprocess.run(
        ["git", "checkout", sha],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Fetch the specific commit and retry
        subprocess.run(
            ["git", "fetch", "origin", sha],
            cwd=workdir,
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "checkout", sha],
            cwd=workdir,
            check=True,
            capture_output=True,
            text=True,
        )


def create_branch(workdir: Path, branch_name: str) -> None:
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=workdir,
        check=True,
        capture_output=True,
        text=True,
    )

def get_diff(workdir: Path) -> str:
    result = subprocess.run(
        ["git", "diff"],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    return result.stdout

def get_changed_files(workdir: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    return [f for f in result.stdout.strip().split("\n") if f]

def commit_changes(workdir: Path, message: str) -> None:
    subprocess.run(
        ["git", "add", "-A"],
        cwd=workdir,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=workdir,
        check=True,
        capture_output=True,
        text=True,
    )
