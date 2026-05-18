"""
CodeClash data utilities.

Download, extract, and build strategy pools from viewer.codeclash.ai.
See tools/codeclash_strategies/ for the public command wrappers and docs.
"""

__all__ = [
    "download_codeclash",
    "extract_strategies",
]


def __getattr__(name):
    if name == "download_codeclash":
        from .download import download_codeclash

        return download_codeclash
    if name == "extract_strategies":
        from .extract import extract_strategies

        return extract_strategies
    raise AttributeError(name)
