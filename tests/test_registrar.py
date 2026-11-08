"""Pruebas unitarias del endpoint de registro (sin AWS)."""

import base64
import json
import os
import unittest
from unittest import mock

os.environ["USER_POOL_ID"] = "us-east-1_test"
os.environ["DEFAULT_GROUP"] = "solicitante"
os.environ["TENANT_CODES"] = json.dumps(
    {
        "ALFA-2026": "empresa-alfa",
        "BETA-2026": "empresa-beta",
    }
)

from src import registrar  # noqa: E402
from src.registrar import ClientError  # noqa: E402


class CognitoFalso:
    """Cliente Cognito en memoria que registra las llamadas."""

    def __init__(self, error_en=None):
        self.llamadas = []
        self.error_en = error_en or {}

    def _registrar(self, nombre, **kwargs):
        self.llamadas.append((nombre, kwargs))
        error = self.error_en.get(nombre)
        if error:
            raise error

    def admin_create_user(self, **kwargs):
        self._registrar("admin_create_user", **kwargs)
        return {"User": {"Username": kwargs["Username"]}}

    def admin_set_user_password(self, **kwargs):
        self._registrar("admin_set_user_password", **kwargs)

    def admin_add_user_to_group(self, **kwargs):
        self._registrar("admin_add_user_to_group", **kwargs)

    def admin_delete_user(self, **kwargs):
        self._registrar("admin_delete_user", **kwargs)

    def nombres(self):
        return [nombre for nombre, _ in self.llamadas]


def error_cognito(codigo, mensaje="error"):
    return ClientError(
        {"Error": {"Code": codigo, "Message": mensaje}}, "Operacion"
    )


class RegistrarTest(unittest.TestCase):
    def evento(self, cuerpo, base64_codificado=False):
        crudo = cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo)
        evento = {"body": crudo}
        if base64_codificado:
            evento["body"] = base64.b64encode(crudo.encode()).decode()
            evento["isBase64Encoded"] = True
        return evento

    def ejecutar(self, cuerpo, cliente=None, **kwargs):
        cliente = cliente or CognitoFalso()
        with mock.patch.object(registrar, "_cliente_cognito", cliente):
            respuesta = registrar.handler(self.evento(cuerpo, **kwargs), None)
        return respuesta, cliente

    def test_registro_exitoso(self):
        respuesta, cliente = self.ejecutar(
            {
                "email": "Nuevo.Alfa@Example.com",
                "password": "Itsm2026!",
                "codigo": "alfa-2026",
            }
        )

        self.assertEqual(respuesta["statusCode"], 201)
        cuerpo = json.loads(respuesta["body"])
        self.assertEqual(cuerpo["tenant_id"], "empresa-alfa")
        self.assertEqual(cuerpo["email"], "nuevo.alfa@example.com")
        self.assertEqual(cuerpo["grupo"], "solicitante")

        self.assertEqual(
            cliente.nombres(),
            [
                "admin_create_user",
                "admin_set_user_password",
                "admin_add_user_to_group",
            ],
        )

        _, alta = cliente.llamadas[0]
        atributos = {a["Name"]: a["Value"] for a in alta["UserAttributes"]}
        self.assertEqual(atributos["custom:tenant_id"], "empresa-alfa")
        self.assertEqual(atributos["email"], "nuevo.alfa@example.com")
        self.assertEqual(atributos["email_verified"], "true")
        self.assertEqual(alta["MessageAction"], "SUPPRESS")
        self.assertEqual(alta["UserPoolId"], "us-east-1_test")

        _, contrasena = cliente.llamadas[1]
        self.assertEqual(contrasena["Password"], "Itsm2026!")
        self.assertTrue(contrasena["Permanent"])

        _, grupo = cliente.llamadas[2]
        self.assertEqual(grupo["GroupName"], "solicitante")

    def test_codigo_invalido_no_crea_usuario(self):
        respuesta, cliente = self.ejecutar(
            {
                "email": "nuevo@example.com",
                "password": "Itsm2026!",
                "codigo": "NO-EXISTE",
            }
        )

        self.assertEqual(respuesta["statusCode"], 400)
        self.assertEqual(cliente.llamadas, [])

    def test_email_duplicado(self):
        cliente = CognitoFalso(
            {"admin_create_user": error_cognito("UsernameExistsException")}
        )
        respuesta, _ = self.ejecutar(
            {
                "email": "nuevo@example.com",
                "password": "Itsm2026!",
                "codigo": "ALFA-2026",
            },
            cliente,
        )

        self.assertEqual(respuesta["statusCode"], 409)
        self.assertIn("ya esta registrado", json.loads(respuesta["body"])["error"])

    def test_contrasena_invalida(self):
        cliente = CognitoFalso(
            {
                "admin_set_user_password": error_cognito(
                    "InvalidPasswordException", "Password does not conform"
                )
            }
        )
        respuesta, _ = self.ejecutar(
            {
                "email": "nuevo@example.com",
                "password": "Itsm2026!",
                "codigo": "ALFA-2026",
            },
            cliente,
        )

        self.assertEqual(respuesta["statusCode"], 400)
        self.assertIn("admin_delete_user", cliente.nombres())

    def test_error_inesperado_hace_rollback(self):
        cliente = CognitoFalso(
            {"admin_add_user_to_group": error_cognito("InternalErrorException")}
        )
        respuesta, _ = self.ejecutar(
            {
                "email": "nuevo@example.com",
                "password": "Itsm2026!",
                "codigo": "ALFA-2026",
            },
            cliente,
        )

        self.assertEqual(respuesta["statusCode"], 502)
        self.assertIn("admin_delete_user", cliente.nombres())

    def test_body_base64(self):
        respuesta, _ = self.ejecutar(
            {
                "email": "nuevo@example.com",
                "password": "Itsm2026!",
                "codigo": "BETA-2026",
            },
            base64_codificado=True,
        )

        self.assertEqual(respuesta["statusCode"], 201)
        self.assertEqual(
            json.loads(respuesta["body"])["tenant_id"], "empresa-beta"
        )

    def test_campos_obligatorios(self):
        casos = [
            {},
            {"email": "nuevo@example.com"},
            {"email": "nuevo@example.com", "password": "Itsm2026!"},
            {"password": "Itsm2026!", "codigo": "ALFA-2026"},
            {"email": "sin-arroba", "password": "Itsm2026!", "codigo": "ALFA-2026"},
            {"email": "a@b.co", "password": "corta", "codigo": "ALFA-2026"},
        ]

        for caso in casos:
            with self.subTest(caso=caso):
                respuesta, cliente = self.ejecutar(caso)
                self.assertEqual(respuesta["statusCode"], 400)
                self.assertEqual(cliente.llamadas, [])

    def test_body_json_invalido(self):
        respuesta, _ = self.ejecutar("{no es json")
        self.assertEqual(respuesta["statusCode"], 400)

    def test_respuesta_tiene_cors(self):
        respuesta, _ = self.ejecutar(
            {
                "email": "nuevo@example.com",
                "password": "Itsm2026!",
                "codigo": "ALFA-2026",
            }
        )
        self.assertEqual(
            respuesta["headers"]["Access-Control-Allow-Origin"], "*"
        )


if __name__ == "__main__":
    unittest.main()
