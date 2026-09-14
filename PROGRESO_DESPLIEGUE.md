# Estado de revisión y despliegue

Actualizado: 12 de septiembre de 2026

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

## Bloqueo de navegadores externos

Se intentó abrir GitHub con Chrome, Edge y Firefox. Ninguno de esos navegadores está habilitado para esta tarea. El navegador interno es el único disponible y mantiene una preferencia guardada que bloquea `github.com` y `railway.app`. La integración de GitHub fue ofrecida, pero todavía figura sin instalar/conectar. El repositorio local está terminado; no se creó aún ningún recurso externo.
