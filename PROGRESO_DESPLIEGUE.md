# Estado de revisión y despliegue

Actualizado: 19 de septiembre de 2026

## Estado actual para retomar primero

- Git funciona con su carpeta estándar `.git`, rama `main`; el remoto `origin` apunta a `https://github.com/Michael2004007/PROFUT.git` y `main` ya fue publicado en GitHub.
- Se resolvió el problema de acceso a Python 3.13 al cambiar los permisos del entorno. La suite completa volvió a ejecutar las dependencias reales, sin reemplazos: **25 pruebas aprobadas con SQLite en 10,13 s** y **25 aprobadas con PostgreSQL 17 en 24,49 s**. Ninguna prueba excluida; la carga real de fotos está incluida.
- `python -m pip check`: ninguna dependencia rota.
- Se creó un servidor PostgreSQL temporal exclusivo para QA en `127.0.0.1:55437`, con dos bases independientes: `profut_qa_migrations` y `profut_qa_tests`. No se utilizó ninguna base del negocio para estas pruebas.
- En la base vacía de QA se ejecutó `flask --app wsgi.py db upgrade`: llegaron todas las migraciones a `081d8ee0ab6f`. `flask --app wsgi.py db check` confirmó que el esquema coincide con los modelos.
- `bootstrap-production` se ejecutó dos veces: creó el administrador inicial la primera vez y no duplicó ni modificó su contraseña en la segunda. `/health` devolvió HTTP 200 con la configuración de producción y PostgreSQL real.
- Al terminar se detuvo el servidor temporal de QA; sus archivos quedaron en `tmp/postgres-qa-f105308abcaf4df79cc0582db934c0f3`, ignorados por Git.
- Estas verificaciones cubren los casos de la suite; no sustituyen una prueba de carga con operadores simultáneos ni la comprobación del entorno remoto.
- **Railway ya tiene infraestructura real para PROFUT**: proyecto privado `PROFUT_SYSTEM`, PostgreSQL en línea con volumen administrado y servicio web `profut-web`, todos independientes de los demás proyectos de la cuenta. El servicio recibió `DATABASE_URL` enlazada internamente a PostgreSQL, `AUTO_SEED=false` y `AUTO_CREATE_DB=false`.
- El 18 de septiembre se completó la configuración del servicio: comando de migración y administrador inicial antes de publicar, Gunicorn, comprobación `/health` con 120 segundos, volumen `profut-web-volume` montado en `/app/app/static/uploads` y dominio HTTPS reservado `https://profut-web-production.up.railway.app`.
- El 19 de septiembre la integración de Railway recibió acceso a GitHub y el servicio quedó conectado correctamente a `Michael2004007/PROFUT`, rama `main`; los futuros cambios enviados a esa rama activarán despliegues automáticos.
- **Publicado en producción el 19 de septiembre de 2026.** Railway aplicó las migraciones, creó de forma idempotente la cuenta administrativa inicial, inició Gunicorn y mostró el estado `Deployment successful`. El enlace público es `https://profut-web-production.up.railway.app`.
- Se verificó desde fuera de Railway: `https://profut-web-production.up.railway.app/health` respondió HTTP 200 con `{"status":"ok"}` y la página principal respondió HTTP 200. Las credenciales y la clave interna se almacenaron únicamente como variables secretas de Railway, nunca en el repositorio.

Las secciones siguientes conservan el historial anterior. El problema de Python y la prueba de foto pendiente que mencionan **ya están resueltos**.

## Etapa actual: validación de producción local

La auditoría de interfaz y flujos principales está cerrada en local. Se probaron Inicio, Agenda, Torneos, Punto de Venta, cuentas, Caja, Productos, Usuarios, Reportes, Configuración, escritorio, móvil y ambos temas.

Correcciones ya cerradas:

- Horarios vencidos bloqueados en pantalla y también en el servidor, con horario de Paraguay.
- Estado de pago visible en reservas: pendiente, parcial o pagado.
- Punto de Venta: se agrega un producto con un toque y los controles de cantidad aparecen solo en el carrito o cuenta.
- Navegación y carga de productos sin recargar ni subir la pantalla.
- Tablas, llaves y reportes adaptados a celular sin cortar información.
- Contraste del modo claro corregido.
- Arranque de producción preparado para crear solo una vez la configuración y el administrador inicial.
- Operaciones críticas protegidas para evitar doble cobro, doble apertura de caja y venta por encima del stock al trabajar varios usuarios.
- 24 flujos automáticos de negocio aprobados nuevamente durante esta revisión: agenda, reservas, pagos, caja, stock, torneos, resultados, llaves y arranque inicial.
- Las migraciones generan SQL PostgreSQL completo desde una base nueva hasta la revisión actual.
- `railway.json` fue validado y el endpoint `/health` devuelve `200` cuando la base responde.
- La revisión final de bloqueos transaccionales confirmó protección de caja, pagos, inscripciones y descuento de stock.

Pendiente antes del despliegue real:

- Repetir la prueba automática de procesamiento de foto cuando se recupere Python 3.13 local; la validación de formulario y experiencia visual ya fue realizada en navegador.
- Crear el servicio PostgreSQL de Railway, asignar variables seguras y hacer el smoke test remoto. Esto no se puede ejecutar sin conectar la cuenta/proyecto de Railway.

## Incidencia de entorno de revisión

El intérprete Python 3.13 instalado en Windows perdió acceso a su biblioteca estándar desde el entorno aislado de pruebas. Además, este entorno no permite descargar un Python alternativo con dependencias. No se modificó la aplicación ni su base de datos por esta incidencia. Como alternativa se ejecutaron 24 de las 25 pruebas con un intérprete aislado; la única excluida requiere la extensión nativa de imágenes de Python 3.13. La prueba se repetirá en el compilado real de Railway.

Railway y PostgreSQL remotos todavía no fueron conectados ni modificados.

## Salida preparada para Railway

La aplicación está preparada para el primer despliegue. Railway debe recibir estas variables antes de publicar:

- `DATABASE_URL`: referencia a la base PostgreSQL creada por Railway.
- `SECRET_KEY`: clave larga, aleatoria y privada.
- `ADMIN_EMAIL`: correo del primer administrador.
- `ADMIN_PASSWORD`: contraseña inicial de al menos 10 caracteres.
- `ADMIN_NAME`: nombre opcional del administrador.
- `AUTO_CREATE_DB=false` y `AUTO_SEED=false`.

Al desplegar, Railway ejecutará primero las migraciones y el bootstrap; luego iniciará Gunicorn y verificará `/health`. Debe añadirse un volumen en `/app/app/static/uploads` para conservar fotos de productos y QR PIX.

No hay todavía un proyecto Railway vinculado ni una CLI de Railway instalada en este equipo, así que el despliegue externo no fue iniciado.

## Intento de lanzamiento

El 12 de septiembre de 2026 se intentó abrir Railway para crear o vincular el proyecto, pero el navegador rechazó el permiso de acceso a `railway.app`. No se realizó ningún cambio externo ni se intentó una vía alternativa. Para continuar con el lanzamiento se debe habilitar ese acceso en el navegador y volver a solicitar el despliegue.

## Publicación de código

Se inicializó el repositorio Git local y se comprobó que `.env`, bases locales, fotos, entornos virtuales y configuración personal del editor están excluidos. El entorno no permite escribir la carpeta interna `.git`, por lo que el commit local no pudo terminarse. También se intentó crear un repositorio privado en GitHub, pero el navegador rechazó el permiso de acceso a `github.com`. No se subió ningún archivo ni se creó un repositorio remoto.

## Repositorio Git terminado

El 14 de septiembre de 2026 se creó una carpeta de metadatos Git separada (`.git-codex`) porque la `.git` original permanece de solo lectura. La rama es `main`, el primer commit es `ff07758` y contiene 99 archivos del sistema. Un escaneo posterior confirmó que no se versionaron secretos, `.env`, bases locales, fotos cargadas, entornos virtuales ni configuración del editor. Falta conectar GitHub para crear el repositorio privado y hacer el primer `push`.

La restricción local fue levantada posteriormente. El historial se movió a la carpeta estándar `.git`, la carpeta vacía anterior quedó preservada como `.git-empty-backup`, la rama sigue siendo `main` y el repositorio quedó limpio en el commit `524ec82`. Git ya funciona normalmente para el usuario de Windows.

## Bloqueo de navegadores externos

Se intentó abrir GitHub con Chrome, Edge y Firefox. Ninguno de esos navegadores está habilitado para esta tarea. El navegador interno es el único disponible y mantiene una preferencia guardada que bloquea `github.com` y `railway.app`. La integración de GitHub fue ofrecida, pero todavía figura sin instalar/conectar. El repositorio local está terminado; no se creó aún ningún recurso externo.
