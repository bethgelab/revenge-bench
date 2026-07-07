"""Harbor agent entrypoint shim for RevengeBench.

The implementation lives in :mod:`revenge_bench.harbor.agent`. This top-level
module keeps Harbor's ``--agent-import-path harbor_agent:HarborRevengeAgent``
working while allowing the integration to be organized as a package inside the
installed ``revenge_bench`` distribution.

For Harbor to import this shim, run Harbor from the repository's ``harbor/``
directory (or add it to ``PYTHONPATH``) with ``revenge_bench`` importable in
the same environment. See ``harbor/README.md``.
"""

__all__ = ["HarborRevengeAgent"]


def __getattr__(name: str):
    if name == "HarborRevengeAgent":
        from revenge_bench.harbor.agent import HarborRevengeAgent

        return HarborRevengeAgent
    raise AttributeError(name)
