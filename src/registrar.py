"""Registro publico de usuarios (POST /registro).

Flujo:

1. El cliente envia ``email``, ``password`` y ``codigo`` de invitacion.
2. La Lambda traduce el codigo a un ``tenant_id`` (nunca se confia en el
   tenant enviado por el cliente).
3. Crea el usuario con ``AdminCreateUser`` incluyendo ``custom:tenant_id``,
   lo deja confirmado y le asigna el grupo ``solicitante``.

Se usa ``AdminCreateUser`` en lugar del trigger ``PreSignUp`` porque Cognito
no permite asignar atributos personalizados desde ese trigger.

Variables de entorno:
    USER_POOL_ID    ID del User Pool (obligatoria).
    TENANT_CODES    JSON con el mapeo codigo -> tenant_id.
    DEFAULT_GROUP   Grupo inicial del usuario (por defecto ``solicitante``).
"""

import json
import os
import re
import secrets

try:
    from botocore.exceptions import ClientError
except ImportError:  # Permite ejecutar las pruebas sin boto3 instalado.
    class ClientError(Exception):  # type: ignore[no-redef]
        def __init__(self, response, operation_name="Operacion"):
            super().__init__(response)
            self.response = response

CODIGOS_POR_DEFECTO = "{}"
GRUPO_POR_DEFECTO = "solicitante"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_cliente_cognito = None


def handler(event, context):
    """Punto de entrada del API Gateway (proxy integration)."""
    try:
        cuerpo = _leer_cuerpo(event)
    except ValueError as error:
        return _respuesta(400, {"error": str(error)})

    error = _validar(cuerpo)
    if error:
        return _respuesta(400, {"error": error})

    email = cuerpo["email"].strip().lower()
    password = cuerpo["password"]
    codigo = cuerpo["codigo"].strip().upper()

    tenant_id = _tenant_desde_codigo(codigo)
    if not tenant_id:
        # Mensaje generico: no revelamos que codigos existen.
        return _respuesta(400, {"error": "Codigo de invitacion invalido"})

    grupo = os.environ.get("DEFAULT_GROUP", GRUPO_POR_DEFECTO)

    try:
        usuario = _crear_usuario(email, password, tenant_id, grupo)
    except ClientError as error:
        codigo_error = error.response.get("Error", {}).get("Code", "")
        if codigo_error == "UsernameExistsException":
            return _respuesta(409, {"error": "El email ya esta registrado"})
        if codigo_error == "InvalidPasswordException":
            detalle = error.response.get("Error", {}).get("Message", "")
            return _respuesta(
                400,
                {
                    "error": "La contrasena no cumple la politica",
                    "detalle": detalle,
                },
            )
        if codigo_error == "InvalidParameterException":
            detalle = error.response.get("Error", {}).get("Message", "")
            return _respuesta(400, {"error": "Datos invalidos", "detalle": detalle})
        return _respuesta(
            502,
            {
                "error": "No se pudo completar el registro",
                "codigo_aws": codigo_error,
            },
        )

    return _respuesta(
        201,
        {
            "mensaje": "Usuario registrado",
            "email": email,
            "tenant_id": tenant_id,
            "grupo": grupo,
            "username": usuario,
        },
    )


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
def _leer_cuerpo(event):
    """Devuelve el JSON del body, aceptando que API Gateway lo base64 codifique."""
    crudo = event.get("body")
    if not crudo:
        raise ValueError("El cuerpo de la solicitud es obligatorio")

    if event.get("isBase64Encoded"):
        import base64

        try:
            crudo = base64.b64decode(crudo).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("El cuerpo no es base64 valido") from error

    try:
        datos = json.loads(crudo)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("El cuerpo debe ser JSON valido") from error

    if not isinstance(datos, dict):
        raise ValueError("El cuerpo debe ser un objeto JSON")
    return datos


def _validar(datos):
    email = str(datos.get("email", "")).strip()
    password = str(datos.get("password", ""))
    codigo = str(datos.get("codigo", "")).strip()

    if not email:
        return "El email es obligatorio"
    if not _EMAIL.match(email):
        return "El email no tiene un formato valido"
    if len(email) > 254:
        return "El email es demasiado largo"
    if not password:
        return "La contrasena es obligatoria"
    if len(password) < 8:
        return "La contrasena debe tener al menos 8 caracteres"
    if not codigo:
        return "El codigo de invitacion es obligatorio"
    return None


# ---------------------------------------------------------------------------
# Cognito
# ---------------------------------------------------------------------------
def _cliente():
    global _cliente_cognito
    if _cliente_cognito is None:
        import boto3

        _cliente_cognito = boto3.client("cognito-idp")
    return _cliente_cognito


def _tenant_desde_codigo(codigo):
    codigos = json.loads(os.environ.get("TENANT_CODES", CODIGOS_POR_DEFECTO))
    return codigos.get(codigo)


def _crear_usuario(email, password, tenant_id, grupo):
    """Crea el usuario, fija la contrasena y lo agrega al grupo.

    Si algo falla despues del alta, se elimina el usuario para no dejar
    registros a medias.
    """
    cognito = _cliente()
    user_pool_id = os.environ["USER_POOL_ID"]

    # Contrasena temporal aleatoria: nunca se usa, se reemplaza enseguida.
    temporal = f"Itsm-{secrets.token_urlsafe(24)}!9"

    creado = False
    try:
        respuesta = cognito.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            TemporaryPassword=temporal,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:tenant_id", "Value": tenant_id},
            ],
            # No enviamos invitacion por correo: evita depender de SES.
            MessageAction="SUPPRESS",
        )
        creado = True

        cognito.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True,
        )
        cognito.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=email,
            GroupName=grupo,
        )
    except ClientError:
        if creado:
            try:
                cognito.admin_delete_user(
                    UserPoolId=user_pool_id, Username=email
                )
            except ClientError:
                # El error original es mas importante que el rollback.
                pass
        raise

    usuario = respuesta.get("User", {})
    return usuario.get("Username", email)


# ---------------------------------------------------------------------------
# Respuesta
# ---------------------------------------------------------------------------
def _respuesta(estado, cuerpo):
    return {
        "statusCode": estado,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(cuerpo, ensure_ascii=False),
    }
