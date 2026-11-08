#!/usr/bin/env python3
"""Obtiene un ID token de Cognito para probar las APIs protegidas.

Uso:
    python3 scripts/obtener_token.py \
        --email agente.alfa@example.com \
        --password 'Itsm2026!' \
        --stage dev --region us-east-1

El token se imprime en stdout (para poder hacer:
    export ID_TOKEN=$(python3 scripts/obtener_token.py ...)
). Con --claims se muestra ademas el payload decodificado en stderr.

Importante: las APIs usan el ID token, NO el access token, porque el
access token no incluye el atributo custom:tenant_id.
"""

import argparse
import base64
import json
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


def decodificar_payload(token):
    """Decodifica el payload de un JWT sin validar la firma (solo para inspeccion)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--claims",
        action="store_true",
        help="Muestra el payload del token (tenant, grupos, sub) en stderr",
    )
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
        respuesta = cognito.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": args.email,
                "PASSWORD": args.password,
            },
        )
    except ClientError as error:
        print(f"Error autenticando: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    if "ChallengeName" in respuesta:
        print(
            f"Se requiere un challenge no soportado: {respuesta['ChallengeName']}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    resultado = respuesta["AuthenticationResult"]
    id_token = resultado["IdToken"]

    if args.claims:
        claims = decodificar_payload(id_token)
        resumen = {
            "sub": claims.get("sub"),
            "email": claims.get("email"),
            "custom:tenant_id": claims.get("custom:tenant_id"),
            "cognito:groups": claims.get("cognito:groups"),
            "token_use": claims.get("token_use"),
            "exp": claims.get("exp"),
        }
        print(json.dumps(resumen, indent=2, ensure_ascii=False), file=sys.stderr)

        if claims.get("token_use") != "id":
            print(
                "ADVERTENCIA: el token no es un ID token.",
                file=sys.stderr,
            )

    print(id_token)


if __name__ == "__main__":
    main()
