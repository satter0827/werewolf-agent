"""Interactive CLI authentication and TOTP commands."""

from __future__ import annotations

from typing import Annotated

import typer

from werewolf_agent.adapters.auth import (
    SupabaseSessionStore,
    enroll_totp,
    list_totp_factors,
    sign_in_with_password,
    verify_totp,
)
from werewolf_agent.adapters.auth import (
    sign_out as end_session,
)
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.settings import get_settings


def sign_in(
    email: Annotated[str, typer.Option(prompt="メールアドレス")] = "",
) -> None:
    """Sign in with a password and complete an enrolled TOTP challenge."""

    def operation() -> None:
        settings = get_settings()
        store = SupabaseSessionStore(settings.supabase_url)
        password = typer.prompt("パスワード", hide_input=True)
        sign_in_with_password(settings, email, password, store=store)
        factors = list_totp_factors(settings, store=store)
        if not factors:
            typer.echo("ログインしました。管理者利用にはTOTP登録が必要です。")
            return
        factor_id = (
            factors[0].id
            if len(factors) == 1
            else typer.prompt(
                "TOTP factor ID",
                default=factors[0].id,
            )
        )
        code = typer.prompt("6桁の多要素認証コード", hide_input=True)
        verify_totp(settings, factor_id, code, store=store)
        typer.echo("多要素認証を確認してログインしました。")

    run_app_command(operation)


def enroll(
    friendly_name: Annotated[
        str,
        typer.Option("--name", help="authenticator端末の識別名"),
    ] = "werewolf-agent-cli",
) -> None:
    """Enroll TOTP for the current member session and verify it once."""

    def operation() -> None:
        settings = get_settings()
        store = SupabaseSessionStore(settings.supabase_url)
        enrollment = enroll_totp(settings, friendly_name=friendly_name, store=store)
        typer.echo("authenticatorへ次のURIを登録してください。")
        typer.echo(enrollment.uri)
        code = typer.prompt("6桁の多要素認証コード", hide_input=True)
        verify_totp(settings, enrollment.factor_id, code, store=store)
        typer.echo("多要素認証を登録しました。")

    run_app_command(operation)


def sign_out() -> None:
    """End the current member session and replace it with a guest session."""

    def operation() -> None:
        settings = get_settings()
        end_session(
            settings,
            store=SupabaseSessionStore(settings.supabase_url),
        )
        typer.echo("ログアウトしました。")

    run_app_command(operation)


__all__ = ["enroll", "sign_in", "sign_out"]
