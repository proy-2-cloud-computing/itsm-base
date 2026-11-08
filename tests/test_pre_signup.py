"""Pruebas unitarias del trigger PreSignUp (sin AWS)."""

import json
import os
import unittest

os.environ["TENANT_CODES"] = json.dumps(
    {
        "ALFA-2026": "empresa-alfa",
        "BETA-2026": "empresa-beta",
    }
)

from src.pre_signup import handler  # noqa: E402


class PreSignUpTest(unittest.TestCase):
    def test_registro_publico_con_codigo_valido(self):
        event = {
            "triggerSource": "PreSignUp_SignUp",
            "request": {
                "userAttributes": {"email": "nuevo@example.com"},
                "clientMetadata": {"tenant_code": "alfa-2026"},
            },
            "response": {},
        }

        resultado = handler(event, None)

        self.assertEqual(
            resultado["response"]["userAttributes"]["custom:tenant_id"],
            "empresa-alfa",
        )
        self.assertTrue(resultado["response"]["autoConfirmUser"])
        self.assertTrue(resultado["response"]["autoVerifyEmail"])

    def test_registro_publico_con_codigo_invalido(self):
        event = {
            "triggerSource": "PreSignUp_SignUp",
            "request": {
                "userAttributes": {"email": "nuevo@example.com"},
                "clientMetadata": {"tenant_code": "NO-EXISTE"},
            },
            "response": {},
        }

        with self.assertRaises(Exception):
            handler(event, None)

    def test_registro_publico_usa_validation_data(self):
        event = {
            "triggerSource": "PreSignUp_SignUp",
            "request": {
                "userAttributes": {"email": "nuevo@example.com"},
                "validationData": {"tenant_code": "BETA-2026"},
            },
            "response": {},
        }

        resultado = handler(event, None)

        self.assertEqual(
            resultado["response"]["userAttributes"]["custom:tenant_id"],
            "empresa-beta",
        )

    def test_admin_create_user_con_tenant(self):
        event = {
            "triggerSource": "PreSignUp_AdminCreateUser",
            "request": {
                "userAttributes": {"custom:tenant_id": "empresa-beta"},
            },
            "response": {},
        }

        resultado = handler(event, None)

        self.assertEqual(
            resultado["request"]["userAttributes"]["custom:tenant_id"],
            "empresa-beta",
        )

    def test_admin_create_user_sin_tenant(self):
        event = {
            "triggerSource": "PreSignUp_AdminCreateUser",
            "request": {"userAttributes": {"email": "admin@example.com"}},
            "response": {},
        }

        with self.assertRaises(Exception):
            handler(event, None)


if __name__ == "__main__":
    unittest.main()
