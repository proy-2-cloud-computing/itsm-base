#!/usr/bin/env python3
"""Crea los usuarios de demo en Cognito para los 2-3 tenants del proyecto.

Uso:
    python3 scripts/crear_usuarios.py --stage dev --region us-east-1

Requiere credenciales AWS con permisos sobre Cognito y CloudFormation
(las mismas que usa `serverless deploy`).

Crea, por cada tenant:
    solicitante.<corto>@example.com
    agente.<corto>@example.com
    aprobador.<corto>@example.com
    admin.<corto>@example.com

Cada usuario recibe el atributo custom:tenant_id y se agrega al grupo
de Cognito con su rol. La contrasena es la misma para todos por defecto.
"""

import argparse
import sys

import boto3
from botocore.exceptions import ClientError

TENANTS = {
    "empresa-alfa": "alfa",
    "empresa-beta": "beta",
    "empresa-gamma": "gamma",
}

ROLES = ["solicitante", "agente", "aprobador", "admin"]

DEFAULT_PASSWORD = "Itsm2026!"


def obtener_outputs(cfn, stack_name):
    """Devuelve los Outputs del stack como diccionario."""
    try:
        respuesta = cfn.describe_stacks(StackName=stack_name)
    except ClientError as error:
        print(
            f"No se pudo leer el stack '{stack_name}'. "
            "Ejecuta primero: npx serverless deploy",
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    stacks = respuesta.get("Stacks", [])
    if not stacks:
        print(f"El stack '{stack_name}' no existe.", file=sys.stderr)
        raise SystemExit(1)

    return {
        salida["OutputKey"]: salida["OutputValue"]
        for salida in stacks[0].get("Outputs", [])
    }


def asegurar_usuario(cognito, pool_id, email, tenant_id, password):
    """Crea el usuario o actualiza sus atributos si ya existe."""
    atributos = [
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "custom:tenant_id", "Value": tenant_id},
    ]

    try:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=atributos,
            MessageAction="SUPPRESS",
        )
        print(f"  creado    {email}")
    except ClientError as error:
        if error.response["Error"]["Code"] != "UsernameExistsException":
            raise
        cognito.admin_update_user_attributes(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=atributos,
        )
        print(f"  existe    {email} (atributos actualizados)")

    cognito.admin_set_user_password(
        UserPoolId=pool_id,
        Username=email,
        Password=password,
        Permanent=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument(
        "--tenants",
        nargs="+",
        choices=list(TENANTS),
        default=list(TENANTS),
        help="Tenants a crear (por defecto los tres)",
    )
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    cfn = session.client("cloudformation")
    cognito = session.client("cognito-idp")

    stack_name = f"itsm-base-{args.stage}"
    outputs = obtener_outputs(cfn, stack_name)
    pool_id = outputs.get("UserPoolId")
    if not pool_id:
        print("El stack no tiene el Output UserPoolId.", file=sys.stderr)
        raise SystemExit(1)

    print(f"User Pool: {pool_id}")
    print(f"Region:    {args.region}\n")

    for tenant_id in args.tenants:
        corto = TENANTS[tenant_id]
        print(f"Tenant {tenant_id}")

        for rol in ROLES:
            email = f"{rol}.{corto}@example.com"
            asegurar_usuario(cognito, pool_id, email, tenant_id, args.password)
            cognito.admin_add_user_to_group(
                UserPoolId=pool_id,
                Username=email,
                GroupName=rol,
            )

        print()

    print("Usuarios listos. Contrasena:", args.password)
    print("\nCredenciales para Postman / frontend:")
    print(f"{'TENANT':<15} {'ROL':<12} {'EMAIL'}")
    for tenant_id in args.tenants:
        corto = TENANTS[tenant_id]
        for rol in ROLES:
            print(f"{tenant_id:<15} {rol:<12} {rol}.{corto}@example.com")

    print(
        "\nPara obtener un ID token:\n"
        "  python3 scripts/obtener_token.py --email agente.alfa@example.com "
        f"--password '{args.password}' --stage {args.stage} --region {args.region}"
    )


if __name__ == "__main__":
    main()
