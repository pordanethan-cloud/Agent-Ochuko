"""
Codebase Pre-Indexer & Repo Memory Service for Agent Ochuko.
Parses AST structure, extracts python function/class symbols, and indexes file trees across workspace repositories.
"""
import ast
import os
import logging
from typing import Dict, Any, List
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SymbolInfo(BaseModel):
    name: str
    symbol_type: str  # function, class, variable
    line_number: int
    file_path: str


class RepoIndexer:
    """Pre-indexes codebase repository structure and symbol definitions."""

    @staticmethod
    def index_python_file(file_path: str) -> List[SymbolInfo]:
        """Indexes symbols in a single Python source file."""
        if not os.path.exists(file_path):
            return []

        symbols = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()

            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    symbols.append(SymbolInfo(name=node.name, symbol_type="function", line_number=node.lineno, file_path=file_path))
                elif isinstance(node, ast.ClassDef):
                    symbols.append(SymbolInfo(name=node.name, symbol_type="class", line_number=node.lineno, file_path=file_path))

            logger.info(f"RepoIndexer extracted {len(symbols)} symbols from {file_path}")
        except Exception as e:
            logger.warning(f"RepoIndexer failed to parse {file_path}: {e}")

        return symbols

    @staticmethod
    def index_directory(dir_path: str) -> List[SymbolInfo]:
        """Scans directory for python files and indexes all symbols."""
        all_symbols = []
        if not os.path.exists(dir_path):
            return all_symbols

        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".py"):
                    fpath = os.path.join(root, file)
                    all_symbols.extend(RepoIndexer.index_python_file(fpath))

        return all_symbols


repo_indexer = RepoIndexer()
