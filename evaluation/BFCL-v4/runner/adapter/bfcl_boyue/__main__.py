import os
import sys

from .registry import register_models
from .search_provider import install_serper_search

register_models()
if os.environ.get("BFCL_SEARCH_PROVIDER", "serper") != "serper":
    raise RuntimeError("this runner supports only BFCL_SEARCH_PROVIDER=serper")
if len(sys.argv) > 1 and sys.argv[1] == "generate":
    install_serper_search()

from bfcl_eval.__main__ import cli

cli()
