"""Trigger PreSignUp de Cognito.

Hay dos caminos:

1. Registro publico (``PreSignUp_SignUp``): exige un codigo de invitacion
   enviado por el frontend en ``ClientMetadata`` (o ``ValidationData``) y
   asigna ``custom:tenant_id`` en el servidor. El cliente nunca envia el
   ``tenant_id``.

2. Usuario creado por un administrador (``PreSignUp_AdminCreateUser``): el
   script de demo ya envia ``custom:tenant_id``; solo se valida que exista.

Si el codigo es invalido se lanza una excepcion y Cognito rechaza el registro.
"""

import json
import os

CODIGOS_POR_DEFECTO = "{}"


def handler(event, context):
    trigger = event.get("triggerSource", "")

    if trigger == "PreSignUp_AdminCreateUser":
        return _permitir_admin_create_user(event)

    if trigger == "PreSignUp_SignUp":
        return _registro_publico(event)

    # Login federado / social no configurado en este proyecto.
    raise Exception("Trigger de registro no soportado")


def _permitir_admin_create_user(event):
    """Los usuarios creados por el script admin ya traen su tenant."""
    tenant_id = (
        event.get("request", {})
        .get("userAttributes", {})
        .get("custom:tenant_id")
    )
    if not tenant_id:
        raise Exception("AdminCreateUser requiere el atributo custom:tenant_id")
    return event


def _registro_publico(event):
    """Valida el codigo de invitacion y asigna el tenant en el servidor."""
    codigos = json.loads(os.environ.get("TENANT_CODES", CODIGOS_POR_DEFECTO))
    request = event.get("request", {})
    metadata = request.get("clientMetadata") or request.get("validationData") or {}

    codigo = str(metadata.get("tenant_code", "")).strip().upper()
    tenant_id = codigos.get(codigo)

    if not tenant_id:
        # El cliente recibe un error generico; no revelamos que codigos existen.
        raise Exception("Codigo de invitacion invalido")

    response = event.setdefault("response", {})
    atributos = response.setdefault("userAttributes", {})
    atributos["custom:tenant_id"] = tenant_id

    # Solo para la demo: evita depender de SES y de la confirmacion por correo.
    # En produccion, quitar autoVerifyEmail y exigir confirmacion.
    response["autoConfirmUser"] = True
    response["autoVerifyEmail"] = True

    return event
