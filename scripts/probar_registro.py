#!/usr/bin/env python3
"""Prueba el endpoint publico de registro sin usar el frontend.

Uso:
    python3 scripts/probar_registro.py \
        --email nuevo.alfa@example.com \
        --password 'Itsm2026!' \
        --codigo ALFA-2026

Lee la URL del Output ``RegistroApiUrl`` del stack ``itsm-base-<stage>``.
Tambien acepta ``--url`` para apuntar a otro entorno.

Despues del registro puedes iniciar sesion con scripts/obtener_token.py.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

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


def post_json(url, datos, timeout=20):
    cuerpo = json.dumps(datos).encode("utf-8")
    solicitud = urllib.request.Request(
        url,
        data=cuerpo,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(solicitud, timeout=timeout) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        print(f"No se pudo conectar con {url}: {error.reason}", file=sys.stderr)
        raise SystemExit(1) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--codigo", required=True)
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--url",
        help="URL del endpoint. Si se omite, se lee del Output RegistroApiUrl.",
    )
    args = parser.parse_args()

    url = args.url
    if not url:
        session = boto3.Session(region_name=args.region)
        outputs = obtener_outputs(
            session.client("cloudformation"), f"itsm-base-{args.stage}"
        )
        url = outputs.get("RegistroApiUrl")
        if not url:
            print(
                "El stack no tiene el Output RegistroApiUrl. "
                "Despliega los cambios con: npx serverless deploy --stage "
                f"{args.stage}",
                file=sys.stderr,
            )
            raise SystemExit(1)

    print(f"POST {url}")
    estado, cuerpo = post_json(
        url,
        {
            "email": args.email,
            "password": args.password,
            "codigo": args.codigo,
        },
    )

    print(f"HTTP {estado}")
    try:
        print(json.dumps(json.loads(cuerpo), indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(cuerpo)

    if estado not in (200, 201):
        raise SystemExit(1)

    print(
        "\nAhora obtén el token con:\n"
        f"  python3 scripts/obtener_token.py --email {args.email} "
        "--password '<tu-password>' --claims"
    )


if __name__ == "__main__":
    main()
