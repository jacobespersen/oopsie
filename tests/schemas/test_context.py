"""Tests for oopsie.schemas.context."""

import pytest
from oopsie.schemas.context import (
    ExceptionEntry,
    ExecutionContext,
    MechanismInfo,
    StackFrame,
)
from pydantic import ValidationError


class TestStackFrame:
    def test_minimal(self):
        frame = StackFrame(file="app/models/user.rb")
        assert frame.file == "app/models/user.rb"
        assert frame.in_app is True
        assert frame.function is None

    def test_full(self):
        frame = StackFrame(
            file="app/models/user.rb",
            function="validate!",
            lineno=42,
            module="User",
            in_app=True,
            context_line="User.find!(id)",
            pre_context=["  def validate!", "    return if valid?"],
            post_context=["    raise ValidationError"],
            vars={"id": 99, "name": "test"},
        )
        assert frame.lineno == 42
        assert frame.vars == {"id": 99, "name": "test"}

    def test_pre_context_max_5_lines(self):
        with pytest.raises(ValidationError):
            StackFrame(file="f.rb", pre_context=["a"] * 6)

    def test_post_context_max_5_lines(self):
        with pytest.raises(ValidationError):
            StackFrame(file="f.rb", post_context=["a"] * 6)

    def test_vars_max_50_keys(self):
        with pytest.raises(ValidationError):
            StackFrame(file="f.rb", vars={f"k{i}": "v" for i in range(51)})


class TestExceptionEntry:
    def test_minimal(self):
        entry = ExceptionEntry(type="NoMethodError", value="undefined method")
        assert entry.type == "NoMethodError"
        assert entry.stacktrace is None

    def test_with_stacktrace(self):
        entry = ExceptionEntry(
            type="NoMethodError",
            value="undefined method",
            stacktrace=[StackFrame(file="app/models/user.rb", lineno=42)],
        )
        assert len(entry.stacktrace) == 1

    def test_stacktrace_max_100_frames(self):
        frames = [StackFrame(file=f"f{i}.rb") for i in range(101)]
        with pytest.raises(ValidationError):
            ExceptionEntry(type="E", value="v", stacktrace=frames)

    def test_with_mechanism(self):
        entry = ExceptionEntry(
            type="E",
            value="v",
            mechanism=MechanismInfo(type="chained", handled=False),
        )
        assert entry.mechanism.type == "chained"
        assert entry.mechanism.handled is False


class TestExecutionContext:
    def test_minimal(self):
        ctx = ExecutionContext(type="http")
        assert ctx.type == "http"
        assert ctx.description is None
        assert ctx.data is None

    def test_full_http(self):
        ctx = ExecutionContext(
            type="http",
            description="POST /api/users",
            data={
                "method": "POST",
                "url": "/api/users",
                "headers": {"content-type": "application/json"},
            },
        )
        assert ctx.data["method"] == "POST"

    def test_worker_context(self):
        ctx = ExecutionContext(
            type="worker",
            description="UserMailer#welcome",
            data={"job_class": "UserMailer", "queue": "mailers"},
        )
        assert ctx.type == "worker"

    def test_data_max_32_keys(self):
        with pytest.raises(ValidationError):
            ExecutionContext(type="http", data={f"k{i}": "v" for i in range(33)})
