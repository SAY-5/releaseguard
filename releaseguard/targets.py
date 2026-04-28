"""Target environment abstractions.

A `Target` is a runnable shell — `Local` for the current process,
`Docker` for an exec into a managed container. Both expose the same
`run(cmd) -> Result` interface so the rest of the code doesn't care
which one it's talking to.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Result:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


class Target(Protocol):
    name: str

    def run(self, cmd: list[str], *, env: dict[str, str] | None = None,
            check: bool = False) -> Result: ...

    def setup(self) -> None: ...
    def teardown(self) -> None: ...


@dataclass
class TargetSpec:
    """The on-disk YAML form, before being turned into a live Target."""

    name: str
    image: str = ""
    inherit_from: str | None = None
    expected_env: dict[str, str] = field(default_factory=dict)
    expected_packages: list[str] = field(default_factory=list)
    expected_files: list[dict] = field(default_factory=list)
    exec_probes: list[str] = field(default_factory=list)
    pytest_args: list[str] = field(default_factory=lambda: ["-q"])

    def merged_with(self, other: "TargetSpec") -> "TargetSpec":
        """Apply `self` *on top of* `other` (self wins on conflicts)."""
        return TargetSpec(
            name=self.name,
            image=self.image or other.image,
            inherit_from=None,
            expected_env={**other.expected_env, **self.expected_env},
            expected_packages=list({*other.expected_packages, *self.expected_packages}),
            expected_files=other.expected_files + self.expected_files,
            exec_probes=other.exec_probes + self.exec_probes,
            pytest_args=self.pytest_args or other.pytest_args,
        )


@dataclass
class Local:
    """The trivial target: run in the current process's shell."""

    name: str = "local"
    extra_env: dict[str, str] = field(default_factory=dict)

    def setup(self) -> None: ...
    def teardown(self) -> None: ...

    def run(self, cmd: list[str], *, env: dict[str, str] | None = None,
            check: bool = False) -> Result:
        e = os.environ.copy()
        e.update(self.extra_env)
        if env:
            e.update(env)
        proc = subprocess.run(
            cmd, capture_output=True, text=True, env=e, check=False,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(
                f"command {cmd!r} failed: rc={proc.returncode}\n{proc.stderr}"
            )
        return Result(code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


@dataclass
class Docker:
    """A long-lived container we keep open across many runs."""

    name: str
    image: str
    extra_env: dict[str, str] = field(default_factory=dict)
    workdir: str = "/work"
    container_id: str = ""
    docker_bin: str = "docker"

    def setup(self) -> None:
        if self.container_id:
            return
        cid = "rg-" + uuid.uuid4().hex[:8]
        cmd = [self.docker_bin, "run", "-d", "--rm", "--name", cid,
               "-w", self.workdir, "--entrypoint", "tail",
               self.image, "-f", "/dev/null"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        self.container_id = proc.stdout.strip() or cid

    def teardown(self) -> None:
        if not self.container_id:
            return
        subprocess.run([self.docker_bin, "kill", self.container_id],
                       capture_output=True, check=False)
        self.container_id = ""

    def run(self, cmd: list[str], *, env: dict[str, str] | None = None,
            check: bool = False) -> Result:
        if not self.container_id:
            self.setup()
        env_args: list[str] = []
        for k, v in (env or {}).items():
            env_args += ["-e", f"{k}={v}"]
        for k, v in self.extra_env.items():
            env_args += ["-e", f"{k}={v}"]
        full = [self.docker_bin, "exec"] + env_args + [self.container_id] + cmd
        proc = subprocess.run(full, capture_output=True, text=True, check=False)
        if check and proc.returncode != 0:
            raise RuntimeError(
                f"docker exec {cmd!r} failed: {proc.stderr}"
            )
        return Result(code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def shell(*tokens: str) -> list[str]:
    """Helper: shell-quote a series of tokens into a single argv."""
    return ["/bin/sh", "-c", " ".join(shlex.quote(t) for t in tokens)]
