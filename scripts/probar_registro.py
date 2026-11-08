#!/usr/bin/env python3
"""Prueba el registro publico contra Cognito sin usar el frontend.

Uso:
    python3 scripts/probar_registro.py \
        --email nuevo.alfa@example.com \
        --password 'Itsm2026!' \
        --codigo ALFA-2026 \
        --stage dev --region us-east-1

Sirve para verificar que el trigger PreSignUp:
  - acepta un codigo valido,
  - asigna custom:tenant_id,
  - rechaza un codigo invalido.

Despues del registro puedes iniciar sesion con scripts/obtener_token.py.
"""

import argparse
import sys

import boto3
from botocore.exceptions import ClientError


def obtener_outputs(cfn, stack_name):
    try:
        respuesta = cfn.describe_stacks(StackName=stack_name)
    except ClientError as error:
        print(f"No se pudo leer el stack '{stack_name}'.", file=sys.stderr)
        raise SystemExit(1) from error

    stacks = respuesta.get("Stacks", [])
    if not stacks:
        print(f"El stack '{stack_name}' no existe.", file=sys.stderr)
        raise SystemExit(1)

    return {
        salida["OutputKey"]: salida["OutputValue"]
        for salida in stacks[0].get("Outputs", [])
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--codigo", required=True)
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    cfn = session.client("cloudformation")
    cognito = session.client("cognito-idp")

    outputs = obtener_outputs(cfn, f"itsm-base-{args.stage}")
    client_id = outputs.get("UserPoolClientId")
    if not client_id:
        print("El stack no tiene el Output UserPoolClientId.", file=sys.stderr)
        raise SystemExit(1)

    try:
        respuesta = cognito.sign_up(
            ClientId=client_id,
            Username=args.email,
            Password=args.password,
            UserAttributes=[{"Name": "email", "Value": args.email}],
            ClientMetadata={"tenant_code": args.codigo},
        )
    except ClientError as error:
        detalle = error.response.get("Error", {})
        codigo = detalle.get("Code", "Desconocido")
        mensaje = detalle.get("Message", str(error))
        print(f"Registro rechazado [{codigo}]: {mensaje}", file=sys.stderr)
        raise SystemExit(1) from error

    print("Registro exitoso")
    print(f"  UserSub:       {respuesta.get('UserSub')}")
    print(f"  UserConfirmed: {respuesta.get('UserConfirmed')}")
    print(
        "\nAhora obtén el token con:\n"
        f"  python3 scripts/obtener_token.py --email {args.email} "
        "--password '<tu-password>' --claims"
    )


if __name__ == "__main__":
    main()
