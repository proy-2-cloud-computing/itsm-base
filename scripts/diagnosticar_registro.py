#!/usr/bin/env python3
"""Diagnostica la configuracion de registro desplegada en AWS.

Uso:
    python3 scripts/diagnosticar_registro.py --stage dev --region us-east-1

Revisa:
  - AllowAdminCreateUserOnly del User Pool (debe ser True: el alta pasa por
    la Lambda de registro, no por auto-registro de Cognito)
  - ausencia del trigger PreSignUp (ya no se usa)
  - atributos del App Client
  - estado y variables de la Lambda registrar
  - que exista el Output RegistroApiUrl

Sirve para explicar por que `probar_registro.py` rechaza un registro.
"""

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError


def obtener_outputs(cfn, stack_name):
    respuesta = cfn.describe_stacks(StackName=stack_name)
    return {
        salida["OutputKey"]: salida["OutputValue"]
        for salida in respuesta["Stacks"][0].get("Outputs", [])
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    cfn = session.client("cloudformation")
    cognito = session.client("cognito-idp")
    lam = session.client("lambda")

    stack_name = f"itsm-base-{args.stage}"

    try:
        outputs = obtener_outputs(cfn, stack_name)
    except ClientError as error:
        print(f"No se pudo leer el stack '{stack_name}': {error}", file=sys.stderr)
        raise SystemExit(1) from error

    pool_id = outputs.get("UserPoolId")
    client_id = outputs.get("UserPoolClientId")
    if not pool_id or not client_id:
        print("Faltan los Outputs UserPoolId / UserPoolClientId.", file=sys.stderr)
        raise SystemExit(1)

    print(f"Stack:  {stack_name}")
    print(f"Region: {args.region}")
    print(f"Pool:   {pool_id}")
    print(f"Client: {client_id}\n")

    pool = cognito.describe_user_pool(UserPoolId=pool_id)["UserPool"]
    admin_only = pool.get("AdminCreateUserConfig", {}).get(
        "AllowAdminCreateUserOnly"
    )
    lambda_config = pool.get("LambdaConfig", {})

    print("=== User Pool ===")
    print(f"AllowAdminCreateUserOnly: {admin_only}")
    print(f"LambdaConfig:             {json.dumps(lambda_config, default=str)}")
    print(f"AutoVerifiedAttributes:   {pool.get('AutoVerifiedAttributes')}")

    if admin_only is not True:
        print(
            "\nPROBLEMA: se esperaba AllowAdminCreateUserOnly=True porque el "
            "alta la hace la Lambda de registro. Despliega los cambios con: "
            f"npx serverless deploy --stage {args.stage}"
        )
    if "PreSignUp" in lambda_config:
        print(
            "\nPROBLEMA: el User Pool aun tiene el trigger PreSignUp. "
            "Despliega los cambios para eliminarlo."
        )

    client = cognito.describe_user_pool_client(
        UserPoolId=pool_id, ClientId=client_id
    )["UserPoolClient"]

    print("\n=== App Client ===")
    print(f"ExplicitAuthFlows: {client.get('ExplicitAuthFlows')}")
    print(f"ReadAttributes:    {client.get('ReadAttributes')}")
    print(f"WriteAttributes:   {client.get('WriteAttributes')}")

    print("\n=== Endpoint de registro ===")
    url = outputs.get("RegistroApiUrl")
    if url:
        print(f"RegistroApiUrl: {url}")
    else:
        print("PROBLEMA: falta el Output RegistroApiUrl. Despliega los cambios.")

    print("\n=== Lambda registrar ===")
    try:
        detalle = cfn.describe_stack_resource(
            StackName=stack_name,
            LogicalResourceId="RegistrarLambdaFunction",
        )["StackResourceDetail"]
        funcion = detalle["PhysicalResourceId"]
        print(f"Funcion: {funcion}")

        configuracion = lam.get_function_configuration(FunctionName=funcion)
        variables = configuracion.get("Environment", {}).get("Variables", {})
        print(f"State:              {configuracion.get('State')}")
        print(f"LastUpdateStatus:   {configuracion.get('LastUpdateStatus')}")
        print(f"USER_POOL_ID:       {variables.get('USER_POOL_ID')}")
        print(f"DEFAULT_GROUP:      {variables.get('DEFAULT_GROUP')}")
        print(f"TENANT_CODES:       {variables.get('TENANT_CODES')}")

        for requerida in ("USER_POOL_ID", "TENANT_CODES"):
            if requerida not in variables:
                print(f"\nPROBLEMA: la Lambda no tiene la variable {requerida}.")
    except ClientError as error:
        if error.response["Error"]["Code"] == "ResourceNotFoundException":
            print(
                "PROBLEMA: no existe la Lambda del registro. "
                "Despliega los cambios."
            )
        else:
            print(f"No se pudo inspeccionar la Lambda: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
