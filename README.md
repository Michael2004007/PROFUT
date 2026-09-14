# PROFUT - Gestión Deportiva

Sistema web responsive para administrar una cancha: reservas, cuentas y cobros parciales, POS, caja, productos, torneos, equipos, jugadores, usuarios, reportes, configuración y auditoría.

## Estado de esta versión

La aplicación ya incluye una V1 operativa de punta a punta:

- autenticación segura, recordarme, bloqueo progresivo y roles `ADMIN`, `OPERADOR` y `VISOR`;
- Dashboard con reservas, ingresos, pendientes, disponibilidad, caja, métodos de pago, alertas y centro de notificaciones;
- Agenda en tres pasos: Mes → Día → Horario;
- reserva con validación de colisión, precio histórico y cuenta automática de cancha;
- cancelación lógica y bloqueos de mantenimiento;
- POS para venta directa y cuentas de reservas, con fotos y búsqueda/alta por código de barras;
- consumos, control transaccional de stock y cobro parcial por ítem/importe;
- Efectivo, Tarjeta, Transferencia y PIX con identificador de idempotencia;
- tickets imprimibles, anulación auditada y restitución de stock en ventas anuladas;
- apertura, movimientos, resumen y cierre de caja con diferencia;
- productos con foto obligatoria, código único, escaneo por cámara o lector físico, umbral de stock y ajustes con motivo;
- equipos con jugadores internos y estado de habilitación;
- torneos con monto de inscripción y cobro, alta de equipo durante la inscripción, sorteo automático, todos contra todos, grupos + eliminación o eliminación directa;
- tablas automáticas (3 puntos victoria, 1 empate), carga de resultados, clasificación, cruces, avance de ganadores y campeón;
- partidos generados que pueden reservar su horario y bloquear automáticamente la Agenda;
- usuarios, contraseñas temporales, permisos y actividad de auditoría;
- reportes filtrables y exportación PDF, XLSX y CSV;
- configuración funcional de cancha, días/horarios, precio, tema persistente, avisos, ticket y QR PIX;
- diseño oscuro/claro responsive con navegación específica para celular;
- migraciones versionadas y pruebas automatizadas de los flujos de mayor riesgo.

## Inicio rápido en Windows

```powershell
cd "C:\Users\oscar\OneDrive\Documents\Python\PROFUT_SYSTEM"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Abrir `http://127.0.0.1:5000`.

Credenciales de demostración:

- Administrador: `admin@profut.local` / `Profut2026!`
- Operador: `operador@profut.local` / `Operador2026!`
- Visor: `visor@profut.local` / `Visor2026!`

Cambiar estas claves antes de cargar datos reales. Si la base ya existe, modificar las contraseñas desde **Usuarios**; las variables `ADMIN_EMAIL` y `ADMIN_PASSWORD` solo se aplican en la primera inicialización.

## Base de datos y comandos

El arranque de desarrollo crea y carga datos de demostración automáticamente. Para un inicio controlado con migraciones:

```powershell
$env:AUTO_CREATE_DB="false"
$env:AUTO_SEED="false"
.\.venv\Scripts\python.exe -m flask --app app.py db upgrade
.\.venv\Scripts\python.exe -m flask --app app.py init-db --demo
```

Ejecutar las pruebas:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Crear un backup local de SQLite:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.py backup-db
```

## Estructura

```text
app.py                  Entrada local
config.py               Ambientes y seguridad de sesión
app/models.py           Entidades y relaciones SQLAlchemy
app/blueprints/         Controladores por módulo
app/services/           Reglas de negocio y transacciones
app/templates/          Interfaz Jinja responsive
app/static/             CSS y JavaScript
migrations/             Evolución versionada de la base
tests/                  Pruebas de negocio y web
instance/profut.db      Base SQLite local (no versionada)
```

Las rutas validan sesión y permisos. Las reglas sensibles están en servicios y cada cobro, reserva, movimiento, cambio de stock o administración de usuarios deja trazabilidad en `AuditLog`.

## Antes de producción

1. Configurar PostgreSQL en `DATABASE_URL`; en producción `AUTO_CREATE_DB` y `AUTO_SEED` ya quedan desactivados por defecto.
2. Definir una `SECRET_KEY` larga y aleatoria.
3. Definir `ADMIN_EMAIL`, `ADMIN_PASSWORD` (mínimo 10 caracteres) y opcionalmente `ADMIN_NAME`; el primer despliegue crea únicamente ese administrador y la configuración base.
4. Railway ejecutará las migraciones y el bootstrap idempotente antes de publicar cada versión mediante `railway.json`.
5. Railway iniciará `wsgi:app` con Gunicorn y comprobará `/health` antes de enviar tráfico.
6. Adjuntar un volumen persistente al servicio web con punto de montaje `/app/app/static/uploads`; allí se conservan las fotos de productos y el QR PIX entre despliegues.
7. Cambiar todas las contraseñas iniciales y revisar permisos.
8. Probar la impresora térmica real y ajustar el CSS de 80 mm si fuera necesario.
9. Activar backups programados tanto para PostgreSQL como para el volumen de archivos.
10. PIX funciona con confirmación manual; una conciliación automática necesita proveedor/API y webhook.

La conexión a Railway y el cambio a PostgreSQL quedan deliberadamente pendientes hasta que la validación funcional local esté cerrada. No se ha realizado ningún despliegue ni conexión externa.

## Decisiones deliberadas de V1

- Una sola cancha, como fija el manual.
- SQLite para desarrollo; PostgreSQL es el destino productivo.
- El QR PIX es una imagen configurada, sin credenciales bancarias.
- Las reservas y operaciones financieras nunca se eliminan físicamente.
- Un pago de una caja cerrada no puede anularse desde la interfaz: requiere un procedimiento de reversión contable controlado.
