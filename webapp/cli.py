from __future__ import annotations

import argparse
import getpass
import os
import sys

from database.config import DatabaseSettings
from webapp.repository import PortalRepository


def prompt_new_password(environment_name: str, label: str) -> str:
    configured = os.getenv(environment_name)
    if configured is not None:
        if len(configured) < 12:
            raise ValueError(f"{environment_name} must contain at least 12 characters.")
        return configured

    while True:
        password = getpass.getpass(f"{label} password (minimum 12 characters): ")
        if len(password) < 12:
            print("비밀번호는 12자 이상이어야 합니다.", file=sys.stderr)
            continue
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("비밀번호가 일치하지 않습니다. 다시 입력해 주세요.", file=sys.stderr)
            continue
        return password


def main() -> None:
    parser = argparse.ArgumentParser(description="NCP report portal administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser("bootstrap-admin")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--display-name", default="MSP Administrator")
    customer_user = subparsers.add_parser("create-customer-user")
    customer_user.add_argument("--email", required=True)
    customer_user.add_argument("--display-name", required=True)
    customer_user.add_argument("--tenant-code", required=True)
    customer_user.add_argument(
        "--role",
        choices=("CUSTOMER_VIEWER", "CUSTOMER_ADMIN"),
        default="CUSTOMER_VIEWER",
    )
    args = parser.parse_args()

    try:
        if args.command == "bootstrap-admin":
            password = prompt_new_password("BOOTSTRAP_MSP_PASSWORD", "Initial MSP")
            repository = PortalRepository(DatabaseSettings.from_env())
            user_id = repository.bootstrap_msp_admin(args.email, password, args.display_name)
            print(f"MSP administrator is ready: {args.email} ({user_id})")
        elif args.command == "create-customer-user":
            password = prompt_new_password("BOOTSTRAP_CUSTOMER_PASSWORD", "Initial customer")
            repository = PortalRepository(DatabaseSettings.from_env())
            user_id = repository.create_customer_user(
                args.email,
                password,
                args.display_name,
                args.tenant_code,
                args.role,
            )
            print(f"Customer user is ready: {args.email} ({user_id})")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
