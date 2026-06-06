"""Tests for agent/config.py — configuration building."""
import os
from argparse import Namespace
from pathlib import Path

import pytest

from agent.config import build_config


class TestBuildConfig:
    def test_basic_config(self):
        args = Namespace(repo="owner/repo", issue=42, base_commit=None, max_iterations=None, model=None)
        cfg = build_config(args)
        assert cfg.repo == "owner/repo"
        assert cfg.issue_number == 42
        assert cfg.base_commit is None
        assert cfg.model == "deepseek/deepseek-v4-pro"
        assert cfg.temperature == 0.0

    def test_output_dir_format(self):
        args = Namespace(repo="go-playground/validator", issue=1550, base_commit=None, max_iterations=None, model=None)
        cfg = build_config(args)
        assert "go-playground_validator" in str(cfg.output_dir)
        assert "issue1550" in str(cfg.output_dir)

    def test_workdir_format(self):
        args = Namespace(repo="gin-gonic/gin", issue=100, base_commit=None, max_iterations=None, model=None)
        cfg = build_config(args)
        assert cfg.workdir == Path("workspace/gin-gonic_gin")

    def test_custom_model(self):
        args = Namespace(repo="r/r", issue=1, base_commit=None, max_iterations=None, model="anthropic/claude-sonnet-4-5")
        cfg = build_config(args)
        assert cfg.model == "anthropic/claude-sonnet-4-5"

    def test_custom_max_iterations(self):
        args = Namespace(repo="r/r", issue=1, base_commit=None, max_iterations=10, model=None)
        cfg = build_config(args)
        assert cfg.max_iterations == 10

    def test_base_commit(self):
        args = Namespace(repo="r/r", issue=1, base_commit="abc123", max_iterations=None, model=None)
        cfg = build_config(args)
        assert cfg.base_commit == "abc123"

    def test_env_model_override(self, monkeypatch):
        monkeypatch.setenv("AGENT_MODEL", "openai/gpt-5.4")
        args = Namespace(repo="r/r", issue=1, base_commit=None, max_iterations=None, model=None)
        cfg = build_config(args)
        assert cfg.model == "openai/gpt-5.4"

    def test_cli_model_overrides_env(self, monkeypatch):
        monkeypatch.setenv("AGENT_MODEL", "openai/gpt-5.4")
        args = Namespace(repo="r/r", issue=1, base_commit=None, max_iterations=None, model="google/gemini-3.5-flash")
        cfg = build_config(args)
        assert cfg.model == "google/gemini-3.5-flash"
