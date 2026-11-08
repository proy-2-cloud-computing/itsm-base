# itsm-base

Infraestructura compartida de la plataforma ITSM (Grupo 6). **No es un
microservicio de negocio**: crea los recursos que usan los 5 microservicios y
una única Lambda, el trigger `PreSignUp` que asigna el tenant en el registro.

## Qué crea

| Recurso | Logical ID | Para qué |
|---|---|---|
| Cognito User Pool | `UserPool` | Login, `custom:tenant_id`, grupos de rol |
| Cognito App Client | `UserPoolClient` | Cliente público para Amplify/Postman |
| Lambda `preSignUp` | `PreSignUpLambdaFunction` | Valida el código de invitación y asigna `custom:tenant_id` |
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

El registro está habilitado (`AllowAdminCreateUserOnly: false`), pero pasa por
el trigger `PreSignUp`: **sin un código válido, Cognito rechaza el registro**.

| Tenant | Código de demo |
|---|---|
| `empresa-alfa` | `ALFA-2026` |
| `empresa-beta` | `BETA-2026` |
| `empresa-gamma` | `GAMMA-2026` |

Flujo:

1. El frontend envía email, contraseña y `tenant_code`.
2. Cognito invoca `PreSignUp` antes de crear el usuario.
3. La Lambda valida el código y asigna `custom:tenant_id` en el servidor.
4. Cognito crea el usuario confirmado (solo para la demo).
5. El usuario inicia sesión normal y su ID token trae el tenant correcto.

El frontend nunca envía `tenant_id`: envía un código que el servidor traduce.

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

Prueba también un código inválido: debe fallar y no crear el usuario.

### Frontend con Amplify v6

```js
import { signUp } from 'aws-amplify/auth';

await signUp({
  username: email,
  password,
  options: {
    userAttributes: { email },
    clientMetadata: { tenant_code: codigo },
  },
});
```

### Pruebas unitarias del trigger

```bash
python3 -m unittest discover -s tests -v
```

## Qué NO incluye (a propósito)

- **Hosted UI de Cognito**: el frontend usa Amplify Auth con
  `USER_PASSWORD_AUTH`/SRP. Si la necesitan, agreguen un
  `AWS::Cognito::UserPoolDomain`.
- **Suscripciones SNS**: cada consumidor crea su cola y su suscripción en su
  propio `serverless.yml` (así lo pide la guía).
- **Microservicios de negocio**: la única Lambda es el trigger `PreSignUp`.

## Notas importantes

- **Bucket**: `DeletionPolicy: Retain`. Si haces `serverless remove`, el bucket
  y sus objetos quedan en la cuenta; bórralos manualmente si quieres limpiar.
- **CORS del bucket**: está en `*` para desarrollo. Restríngelo al dominio de
  Amplify antes de la entrega final.
- **`tenant_id`**: el App Client solo permite leer `custom:tenant_id`; no
  permite escribirlo, para que el usuario no pueda cambiar de tenant.
- **Registro público**: un código inválido rechaza el registro. Los usuarios
  creados por `crear_usuarios.py` siguen funcionando porque el handler permite
  el trigger `PreSignUp_AdminCreateUser`.
- **Códigos de invitación**: en la demo están en la variable `TENANT_CODES` del
  `serverless.yml`. En producción usa SSM Parameter Store y rótalos.
- **Auto-confirmación**: `autoConfirmUser` y `autoVerifyEmail` son solo para la
  demo. En producción quita `autoVerifyEmail` y exige confirmación por correo.
- **AWS Academy / Learner Lab**: `provider.iam.role` apunta a
  `arn:aws:iam::${aws:accountId}:role/LabRole`. En una cuenta normal elimina ese
  bloque para que Serverless cree el rol. Verifica también que Cognito esté
  habilitado en tu laboratorio. Si no lo está, este stack fallará al crear el
  User Pool.
- **Región**: todos los servicios deben desplegarse en la misma región para que
  las referencias `${cf:...}` funcionen.
