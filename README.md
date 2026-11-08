# itsm-base

Infraestructura compartida de la plataforma ITSM (Grupo 6). **No es un
microservicio de negocio**: crea los recursos que usan los 5 microservicios y
una única Lambda, `registrar`, que expone `POST /registro` para crear usuarios
con código de invitación y asignarles su tenant.

## Qué crea

| Recurso | Logical ID | Para qué |
|---|---|---|
| Cognito User Pool | `UserPool` | Login, `custom:tenant_id`, grupos de rol |
| Cognito App Client | `UserPoolClient` | Cliente público para Amplify/Postman |
| Lambda `registrar` + `POST /registro` | `RegistrarLambdaFunction` | Valida el código de invitación, crea el usuario y asigna `custom:tenant_id` |
| Grupos Cognito | `GrupoSolicitante`, `GrupoAgente`, `GrupoAprobador`, `GrupoAdmin` | Autorización por rol |
| Topic SNS | `CambiosTopic` | Eventos de `itsm-cambios` |
| Topic SNS | `SolicitudesTopic` | Eventos de `itsm-solicitudes` |
| Topic SNS | `IncidentesTopic` | Eventos de `itsm-incidentes` |
| Topic SNS | `ProblemasTopic` | Eventos de `itsm-problemas` |
| Bucket S3 | `AdjuntosBucket` | Adjuntos con prefijo por tenant |
| — | `Outputs` | ARNs, IDs y nombre de bucket para los demás stacks |

## Requisitos

- Node.js 20+ y npm
- Python 3.10+ con `boto3` (solo para los scripts de demo)
- Credenciales AWS con permisos para crear Cognito, S3 y SNS
- Serverless Framework v4

```bash
npm install
python3 -m pip install -r requirements.txt
```

> **Serverless v4**: si al ejecutar pide una licencia, haz `npx serverless login`
> (es gratuito para uso individual/estudiantil). Si tu curso no permite v4,
> instala `npm i -D serverless@3` y cambia `frameworkVersion: '4'` por `'3'`
> en `serverless.yml`.

## Desplegar

```bash
npx serverless deploy --stage dev
```

El stack se llama `itsm-base-dev` y se crea en `us-east-1` por defecto.

Para ver los outputs:

```bash
npx serverless info --verbose
```

## Outputs y cómo los consumen los otros servicios

| Output | Ejemplo de valor | Quién lo usa |
|---|---|---|
| `UserPoolArn` | `arn:aws:cognito-idp:...` | Authorizer de cada microservicio |
| `UserPoolId` | `us-east-1_abc123` | Scripts de usuarios |
| `UserPoolClientId` | `7abc...` | Frontend / Postman / scripts de token |
| `CambiosTopicArn` | `arn:aws:sns:...` | `itsm-cambios` |
| `SolicitudesTopicArn` | `arn:aws:sns:...` | `itsm-solicitudes` |
| `IncidentesTopicArn` | `arn:aws:sns:...` | `itsm-incidentes` |
| `ProblemasTopicArn` | `arn:aws:sns:...` | `itsm-problemas` |
| `AdjuntosBucketName` | `itsm-base-dev-adjuntosbucket-...` | Todos los que firman URLs |
| `AdjuntosBucketArn` | `arn:aws:s3:::...` | Políticas IAM |
| `RegistroApiUrl` | `https://xxx.execute-api.us-east-1.amazonaws.com/dev/registro` | Frontend y scripts de prueba |
| `Region` | `us-east-1` | Scripts |

En otro `serverless.yml`:

```yaml
environment:
  TOPIC_ARN: ${cf:itsm-base-dev.SolicitudesTopicArn}
  BUCKET: ${cf:itsm-base-dev.AdjuntosBucketName}
```

```yaml
authorizer:
  name: cognitoAuth
  arn: ${cf:itsm-base-dev.UserPoolArn}
```

También se exportan con nombre `itsm-dev-<Output>` para `Fn::ImportValue`.

> El nombre del stack es `itsm-base-<stage>`. Si despliegas con otro stage,
> cambia `dev` por ese stage en las referencias.

## Crear usuarios de demo

Crea 4 usuarios por tenant (`solicitante`, `agente`, `aprobador`, `admin`),
cada uno con `custom:tenant_id` y en su grupo de Cognito:

```bash
python3 scripts/crear_usuarios.py --stage dev --region us-east-1
```

Credenciales por defecto:

| Tenant | Rol | Email | Contraseña |
|---|---|---|---|
| `empresa-alfa` | solicitante | `solicitante.alfa@example.com` | `Itsm2026!` |
| `empresa-alfa` | agente | `agente.alfa@example.com` | `Itsm2026!` |
| `empresa-alfa` | aprobador | `aprobador.alfa@example.com` | `Itsm2026!` |
| `empresa-alfa` | admin | `admin.alfa@example.com` | `Itsm2026!` |
| `empresa-beta` | solicitante | `solicitante.beta@example.com` | `Itsm2026!` |
| `empresa-beta` | agente | `agente.beta@example.com` | `Itsm2026!` |
| `empresa-beta` | aprobador | `aprobador.beta@example.com` | `Itsm2026!` |
| `empresa-beta` | admin | `admin.beta@example.com` | `Itsm2026!` |
| `empresa-gamma` | ... | `...gamma@example.com` | `Itsm2026!` |

Para crear solo dos tenants (demo):

```bash
python3 scripts/crear_usuarios.py --tenants empresa-alfa empresa-beta
```

## Obtener un ID token

Las APIs deben recibir el **ID token**, no el access token, porque el access
token no incluye `custom:tenant_id`.

```bash
python3 scripts/obtener_token.py \
  --email agente.alfa@example.com \
  --password 'Itsm2026!' \
  --stage dev --region us-east-1 \
  --claims
```

- El token sale por **stdout**.
- Los claims (`tenant_id`, `cognito:groups`, `sub`) salen por **stderr** con
  `--claims`.

Para guardarlo:

```bash
export ID_TOKEN=$(python3 scripts/obtener_token.py \
  --email agente.alfa@example.com --password 'Itsm2026!')

curl -H "Authorization: $ID_TOKEN" https://<api>/solicitudes
```

## Registro público con código de invitación

El registro se hace con `POST /registro`, no con el auto-registro de Cognito.
El User Pool tiene `AllowAdminCreateUserOnly: true`: la Lambda `registrar` crea
el usuario con `AdminCreateUser` y asigna `custom:tenant_id` en el servidor.

> **Por qué no se usa el trigger `PreSignUp`**: Cognito solo acepta
> `autoConfirmUser`, `autoVerifyEmail` y `autoVerifyPhone` en su respuesta. Si
> se devuelven `userAttributes`, el registro falla con
> `InvalidLambdaResponseException: Unrecognizable lambda output`.

| Tenant | Código de demo |
|---|---|
| `empresa-alfa` | `ALFA-2026` |
| `empresa-beta` | `BETA-2026` |
| `empresa-gamma` | `GAMMA-2026` |

Flujo:

1. El frontend envía email, contraseña y `codigo` a `POST /registro`.
2. La Lambda traduce el código a `tenant_id` y valida la solicitud.
3. `AdminCreateUser` crea el usuario con `custom:tenant_id` y `email_verified`.
4. `AdminSetUserPassword` fija la contraseña definitiva.
5. `AdminAddUserToGroup` lo agrega al grupo `solicitante`.
6. El usuario inicia sesión normal y su ID token trae el tenant correcto.

El frontend nunca envía `tenant_id`: envía un código que el servidor traduce.

### Contrato del endpoint

```http
POST /registro
Content-Type: application/json
```

```json
{
  "email": "nuevo.alfa@example.com",
  "password": "Itsm2026!",
  "codigo": "ALFA-2026"
}
```

Respuesta `201`:

```json
{
  "mensaje": "Usuario registrado",
  "email": "nuevo.alfa@example.com",
  "tenant_id": "empresa-alfa",
  "grupo": "solicitante",
  "username": "nuevo.alfa@example.com"
}
```

| Estado | Cuándo |
|---|---|
| `201` | Usuario creado |
| `400` | Campos faltantes, JSON inválido, contraseña débil o código inválido |
| `409` | El email ya está registrado |
| `502` | Error inesperado de Cognito (se revierte el alta) |

### Probar sin frontend

```bash
python3 scripts/probar_registro.py \
  --email nuevo.alfa@example.com \
  --password 'Itsm2026!' \
  --codigo ALFA-2026
```

Luego:

```bash
python3 scripts/obtener_token.py \
  --email nuevo.alfa@example.com \
  --password 'Itsm2026!' \
  --claims
```

Prueba también un código inválido: debe devolver `400` y no crear el usuario.

### Frontend

```js
const respuesta = await fetch(`${REGISTRO_API_URL}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password, codigo }),
});

const datos = await respuesta.json();
if (!respuesta.ok) {
  throw new Error(datos.error);
}
```

Después del registro, inicia sesión con Amplify (`signIn`) como cualquier otro
usuario. La pantalla solo necesita: email, contraseña y "código de empresa".

### Pruebas unitarias

```bash
python3 -m unittest discover -s tests -v
```

### Si el registro es rechazado

Primero ejecuta el diagnóstico:

```bash
python3 scripts/diagnosticar_registro.py --stage dev --region us-east-1
```

Debe mostrar:

- `AllowAdminCreateUserOnly: True`
- `LambdaConfig: {}` (sin `PreSignUp`)
- `RegistroApiUrl`
- `USER_POOL_ID` y `TENANT_CODES` en la Lambda `registrar`

Errores comunes:

| Código / mensaje | Causa | Solución |
|---|---|---|
| `HTTP 403 Missing Authentication Token` | La ruta o el método no existen | Despliega y revisa `RegistroApiUrl` |
| `HTTP 400 Codigo de invitacion invalido` | El código no coincide | Usa `ALFA-2026`, `BETA-2026` o `GAMMA-2026` |
| `HTTP 409 El email ya esta registrado` | El email ya existe | Usa otro email |
| `HTTP 400 La contrasena no cumple la politica` | Contraseña débil | 8+, mayúscula, minúscula, número |
| `HTTP 502 No se pudo completar el registro` | Falla de Cognito o del rol IAM | Revisa los logs de la Lambda |
| `AccessDeniedException` en logs | `LabRole` no permite acciones de Cognito | Habilita los permisos en el laboratorio |

Para ver los logs:

```bash
npx serverless logs -f registrar --stage dev --tail
```

## Qué NO incluye (a propósito)

- **Hosted UI de Cognito**: el frontend usa Amplify Auth con
  `USER_PASSWORD_AUTH`/SRP. Si la necesitan, agreguen un
  `AWS::Cognito::UserPoolDomain`.
- **Suscripciones SNS**: cada consumidor crea su cola y su suscripción en su
  propio `serverless.yml` (así lo pide la guía).
- **Microservicios de negocio**: la única Lambda es `registrar`.

## Notas importantes

- **Bucket**: `DeletionPolicy: Retain`. Si haces `serverless remove`, el bucket
  y sus objetos quedan en la cuenta; bórralos manualmente si quieres limpiar.
- **CORS del bucket**: está en `*` para desarrollo. Restríngelo al dominio de
  Amplify antes de la entrega final.
- **`tenant_id`**: el App Client solo permite leer `custom:tenant_id`; no
  permite escribirlo, para que el usuario no pueda cambiar de tenant.
- **Registro público**: solo `POST /registro` puede crear usuarios; el
  auto-registro de Cognito está deshabilitado. Los usuarios de
  `crear_usuarios.py` se crean igual con `AdminCreateUser`.
- **Códigos de invitación**: en la demo están en la variable `TENANT_CODES` del
  `serverless.yml`. En producción usa SSM Parameter Store y rótalos.
- **Confirmación de email**: la Lambda marca `email_verified=true` y usa
  `MessageAction=SUPPRESS` para no depender de SES. En producción envía la
  invitación y exige verificación.
- **Rol IAM**: `LabRole` debe permitir `cognito-idp:AdminCreateUser`,
  `AdminSetUserPassword`, `AdminAddUserToGroup` y `AdminDeleteUser`. Si tu
  laboratorio no lo permite, agrega esas acciones a la política del rol.
- **AWS Academy / Learner Lab**: `provider.iam.role` apunta a
  `arn:aws:iam::${aws:accountId}:role/LabRole`. En una cuenta normal elimina ese
  bloque para que Serverless cree el rol. Verifica también que Cognito esté
  habilitado en tu laboratorio. Si no lo está, este stack fallará al crear el
  User Pool.
- **Región**: todos los servicios deben desplegarse en la misma región para que
  las referencias `${cf:...}` funcionen.
