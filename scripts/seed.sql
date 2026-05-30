-- =============================================================================
-- seed.sql
-- Static seed data for ptc-alcaldias-backend.
-- Safe to run multiple times (all INSERTs use ON CONFLICT DO NOTHING).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Immutability trigger for audit_logs
--    The table itself is managed by Alembic; we only create the trigger
--    function and attach the trigger here.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs table is append-only: % operations are forbidden', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs;
CREATE TRIGGER audit_logs_immutable
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- ---------------------------------------------------------------------------
-- 2. Report categorias
-- ---------------------------------------------------------------------------

INSERT INTO categorias (id, label, color, icono, peso)
VALUES
    ('bacheo',      'Bacheo',                   '#9F2241', 'Construction',  0.22),
    ('alumbrado',   'Alumbrado público',        '#BC955C', 'Lightbulb',    0.16),
    ('limpia',      'Recolección y limpia',     '#2D7A4F', 'Trash2',       0.14),
    ('seguridad',   'Seguridad ciudadana',      '#C03A3A', 'ShieldAlert',  0.12),
    ('agua',        'Fugas y abasto de agua',   '#3A8DC0', 'Droplets',     0.10),
    ('parques',     'Áreas verdes y parques',   '#6B2D8E', 'Trees',        0.06),
    ('arboles',     'Arbolado urbano',          '#3F7D44', 'TreePine',     0.06),
    ('drenaje',     'Drenaje y alcantarillado', '#4A4A6B', 'Waves',        0.05),
    ('semaforos',   'Semáforos y señalización', '#D97706', 'TrafficCone',  0.05),
    ('comercio_vp', 'Comercio en vía pública',  '#7A5C2E', 'Store',        0.04)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. Obra categorias
-- ---------------------------------------------------------------------------

INSERT INTO obra_categorias (id, label, color, peso)
VALUES
    ('pavimentacion',     'Pavimentación',        '#9F2241', 0.22),
    ('drenaje',           'Drenaje y alcantarillado', '#4A4A6B', 0.14),
    ('alumbrado',         'Alumbrado público',    '#BC955C', 0.12),
    ('agua_potable',      'Agua potable',         '#3A8DC0', 0.10),
    ('parques',           'Parques y áreas verdes', '#2D7A4F', 0.10),
    ('escuelas',          'Escuelas',             '#6B2D8E', 0.08),
    ('edificios_publicos','Edificios públicos',   '#7A5C2E', 0.06),
    ('vialidad',          'Vialidades y puentes', '#C03A3A', 0.10),
    ('imagen_urbana',     'Imagen urbana',        '#D97706', 0.08)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. Contratistas
-- ---------------------------------------------------------------------------

INSERT INTO contratistas (id, razon_social, rfc, calificacion)
VALUES
    ('CT01', 'Construcciones Tlalpan S.A. de C.V.',    'CTL920304A12', 4.6),
    ('CT02', 'Pavimentos del Valle S.C.',               'PVA850712D87', 4.2),
    ('CT03', 'Servicios Hidráulicos Xochimilco',        'SHX011024K22', 4.4),
    ('CT04', 'Iluminación Urbana de México',            'IUM930115R43', 4.8),
    ('CT05', 'Grupo Constructor Magdalena',              'GCM030619P54', 4.3),
    ('CT06', 'Proyectos Verdes CDMX',                   'PVC141005H65', 4.5)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 5. Notificaciones
--    ~8-10 por usuario, mezcla de tipos y estados leida/no-leida.
--    Fechas relativas a 2026-05-20 (fecha de referencia del dataset).
--    IMPORTANTE: se ejecuta DESPUES de seed.py (depende de users, reportes, obras).
-- ---------------------------------------------------------------------------

INSERT INTO notificaciones (id, user_id, tenant_id, tipo, titulo, cuerpo, href, entity_type, entity_id, leida, fecha) VALUES

-- ═══════════════════════════════════════════════════════════════════════════
-- MC-ADMIN  ·  Fernando Mercado Guaida
-- ═══════════════════════════════════════════════════════════════════════════
('n-mc-adm-01', 'mc-admin', 'magdalena-contreras', 'alerta',
 'SLA en riesgo: Bache en vialidad principal',
 'El reporte MC-RC-0528 (prioridad alta) lleva más de 52 h sin atención. Límite SLA: 48 h.',
 '/backoffice/reportes/MC-RC-0528', 'reporte', 'MC-RC-0528', false,
 '2026-05-20T09:15:00+00'),

('n-mc-adm-02', 'mc-admin', 'magdalena-contreras', 'alerta',
 'SLA en riesgo: Coladera tapada',
 'El reporte MC-RC-0113 (prioridad alta, drenaje) excede el tiempo de respuesta comprometido.',
 '/backoffice/reportes/MC-RC-0113', 'reporte', 'MC-RC-0113', false,
 '2026-05-20T08:40:00+00'),

('n-mc-adm-03', 'mc-admin', 'magdalena-contreras', 'reporte',
 'Nuevo reporte: Coladera tapada',
 'Ciudadano reportó coladera tapada en San Bernabé Ocotepec. Folio MC-2026-0358.',
 '/backoffice/reportes/MC-RC-0358', 'reporte', 'MC-RC-0358', false,
 '2026-05-20T10:30:00+00'),

('n-mc-adm-04', 'mc-admin', 'magdalena-contreras', 'reporte',
 'Nuevo reporte: Luminaria sin funcionar',
 'Se recibió reporte de luminaria apagada en la zona norte. Folio MC-2026-0634.',
 '/backoffice/reportes/MC-RC-0634', 'reporte', 'MC-RC-0634', false,
 '2026-05-20T10:05:00+00'),

('n-mc-adm-05', 'mc-admin', 'magdalena-contreras', 'cierre',
 'Reporte resuelto: Bache de gran tamaño',
 'Cuadrilla 1 cerró el reporte MC-RC-0655 en San Jerónimo Lídice. Tiempo de atención: 38 h.',
 '/backoffice/reportes/MC-RC-0655', 'reporte', 'MC-RC-0655', true,
 '2026-05-19T22:10:00+00'),

('n-mc-adm-06', 'mc-admin', 'magdalena-contreras', 'obra',
 'Obra en ejecución: Macromedidor Barrio Las Calles',
 'La obra MC-OB-032 inició fase de instalación. Avance actual: 28 %.',
 '/backoffice/obras/MC-OB-032', 'obra', 'MC-OB-032', true,
 '2026-05-18T14:00:00+00'),

('n-mc-adm-07', 'mc-admin', 'magdalena-contreras', 'obra',
 'Avance de obra: Toma domiciliaria La Carbonera',
 'La obra MC-OB-027 alcanzó 78 % de avance. Contratista reporta cierre próximo.',
 '/backoffice/obras/MC-OB-027', 'obra', 'MC-OB-027', true,
 '2026-05-17T10:30:00+00'),

('n-mc-adm-08', 'mc-admin', 'magdalena-contreras', 'cierre',
 'Reporte resuelto: Vehículo abandonado',
 'Caso MC-RC-0150 (seguridad) cerrado tras coordinación con SSC-CDMX.',
 '/backoffice/reportes/MC-RC-0150', 'reporte', 'MC-RC-0150', true,
 '2026-05-17T08:45:00+00'),

('n-mc-adm-09', 'mc-admin', 'magdalena-contreras', 'alerta',
 'Resumen diario: 12 reportes nuevos ayer',
 'Se recibieron 12 reportes el 19 de mayo. 3 clasificados como alta prioridad. Revise la bandeja.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

('n-mc-adm-10', 'mc-admin', 'magdalena-contreras', 'reporte',
 'Nuevo reporte: Árbol con ramas peligrosas',
 'Reporte MC-RC-0080 en zona de conservación. Requiere evaluación de medio ambiente.',
 '/backoffice/reportes/MC-RC-0080', 'reporte', 'MC-RC-0080', false,
 '2026-05-20T09:50:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- MC-DIR-OBRAS  ·  Ing. Adriana Belmont  (areas: bacheo)
-- ═══════════════════════════════════════════════════════════════════════════
('n-mc-do-01', 'mc-dir-obras', 'magdalena-contreras', 'alerta',
 'SLA en riesgo: Bache en vialidad principal',
 'MC-RC-0528 supera las 48 h sin resolución. Asigne cuadrilla urgente.',
 '/backoffice/reportes/MC-RC-0528', 'reporte', 'MC-RC-0528', false,
 '2026-05-20T09:15:00+00'),

('n-mc-do-02', 'mc-dir-obras', 'magdalena-contreras', 'alerta',
 'SLA en riesgo: Hundimiento de pavimento',
 'MC-RC-0404 lleva más de 50 h abierto. Categoría bacheo, prioridad alta.',
 '/backoffice/reportes/MC-RC-0404', 'reporte', 'MC-RC-0404', false,
 '2026-05-20T08:30:00+00'),

('n-mc-do-03', 'mc-dir-obras', 'magdalena-contreras', 'cierre',
 'Reporte resuelto: Bache de gran tamaño',
 'La Cuadrilla 1 completó la reparación de MC-RC-0655. Evidencia fotográfica registrada.',
 '/backoffice/reportes/MC-RC-0655', 'reporte', 'MC-RC-0655', true,
 '2026-05-19T22:10:00+00'),

('n-mc-do-04', 'mc-dir-obras', 'magdalena-contreras', 'cierre',
 'Reporte resuelto: Bache de gran tamaño',
 'MC-RC-0105 cerrado exitosamente. Carpeta asfáltica reparada.',
 '/backoffice/reportes/MC-RC-0105', 'reporte', 'MC-RC-0105', true,
 '2026-05-19T16:00:00+00'),

('n-mc-do-05', 'mc-dir-obras', 'magdalena-contreras', 'reporte',
 'Nuevo reporte de bacheo asignado',
 '3 reportes nuevos de bacheo ingresaron hoy. Revise la bandeja para asignar cuadrillas.',
 '/backoffice/bandeja', null, null, false,
 '2026-05-20T10:00:00+00'),

('n-mc-do-06', 'mc-dir-obras', 'magdalena-contreras', 'obra',
 'Avance de obra: Toma domiciliaria La Cruz',
 'MC-OB-020 reporta avance en obra de agua potable vinculada a su área.',
 '/backoffice/obras/MC-OB-020', 'obra', 'MC-OB-020', true,
 '2026-05-18T11:00:00+00'),

('n-mc-do-07', 'mc-dir-obras', 'magdalena-contreras', 'alerta',
 'Resumen: 8 reportes de bacheo pendientes',
 'Tiene 8 reportes de bacheo en estado nuevo o asignado. 2 en riesgo de SLA.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- MC-DIR-ALUMBRADO  ·  Ing. Roberto Huerta  (areas: alumbrado, semaforos)
-- ═══════════════════════════════════════════════════════════════════════════
('n-mc-da-01', 'mc-dir-alumbrado', 'magdalena-contreras', 'reporte',
 'Nuevo reporte: Luminaria sin funcionar',
 'MC-RC-0634 reporta luminaria apagada. Zona norte, posible falla en tablero.',
 '/backoffice/reportes/MC-RC-0634', 'reporte', 'MC-RC-0634', false,
 '2026-05-20T10:05:00+00'),

('n-mc-da-02', 'mc-dir-alumbrado', 'magdalena-contreras', 'reporte',
 'Nuevo reporte: Tablero eléctrico expuesto',
 'MC-RC-0668 indica cableado descubierto en poste. Riesgo eléctrico para peatones.',
 '/backoffice/reportes/MC-RC-0668', 'reporte', 'MC-RC-0668', false,
 '2026-05-20T09:30:00+00'),

('n-mc-da-03', 'mc-dir-alumbrado', 'magdalena-contreras', 'alerta',
 'SLA en riesgo: Luminaria sin funcionar',
 'MC-RC-0262 (prioridad alta) lleva 60 h sin atender. Límite: 48 h.',
 '/backoffice/reportes/MC-RC-0262', 'reporte', 'MC-RC-0262', false,
 '2026-05-20T08:20:00+00'),

('n-mc-da-04', 'mc-dir-alumbrado', 'magdalena-contreras', 'obra',
 'Obra de alumbrado: Desazolve Barrio Las Calles',
 'MC-OB-018 incluye trabajos en zona de alumbrado. Coordine con la cuadrilla 2.',
 '/backoffice/obras/MC-OB-018', 'obra', 'MC-OB-018', true,
 '2026-05-18T09:00:00+00'),

('n-mc-da-05', 'mc-dir-alumbrado', 'magdalena-contreras', 'alerta',
 'Resumen: 5 reportes de alumbrado pendientes',
 'Tiene 5 reportes de alumbrado/semáforos abiertos. 1 en prioridad crítica.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

('n-mc-da-06', 'mc-dir-alumbrado', 'magdalena-contreras', 'cierre',
 'Cuadrilla 2 cerró reporte de semáforo',
 'Reparación de semáforo completada en cruce escolar. Caso cerrado.',
 '/backoffice/reportes/MC-RC-0262', 'reporte', 'MC-RC-0262', true,
 '2026-05-17T15:30:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- MC-DIR-AGUA  ·  Ing. Patricia Galván  (areas: agua, drenaje)
-- ═══════════════════════════════════════════════════════════════════════════
('n-mc-dag-01', 'mc-dir-agua', 'magdalena-contreras', 'alerta',
 'SLA en riesgo: Agua sucia o turbia',
 'MC-RC-0438 (prioridad alta, agua) supera el tiempo de SLA. Requiere atención urgente.',
 '/backoffice/reportes/MC-RC-0438', 'reporte', 'MC-RC-0438', false,
 '2026-05-20T08:45:00+00'),

('n-mc-dag-02', 'mc-dir-agua', 'magdalena-contreras', 'reporte',
 'Nuevo reporte: Coladera tapada',
 'MC-RC-0358 en San Bernabé Ocotepec. Riesgo de encharcamiento en temporada de lluvias.',
 '/backoffice/reportes/MC-RC-0358', 'reporte', 'MC-RC-0358', false,
 '2026-05-20T10:30:00+00'),

('n-mc-dag-03', 'mc-dir-agua', 'magdalena-contreras', 'reporte',
 'Nuevo reporte: Coladera tapada',
 'MC-RC-0113 reporta drenaje obstruido. Zona baja, prioridad alta.',
 '/backoffice/reportes/MC-RC-0113', 'reporte', 'MC-RC-0113', false,
 '2026-05-20T09:00:00+00'),

('n-mc-dag-04', 'mc-dir-agua', 'magdalena-contreras', 'obra',
 'Obra en ejecución: Macromedidor Tierra Unida',
 'MC-OB-029 avanza según cronograma. Contratista en sitio.',
 '/backoffice/obras/MC-OB-029', 'obra', 'MC-OB-029', true,
 '2026-05-18T16:00:00+00'),

('n-mc-dag-05', 'mc-dir-agua', 'magdalena-contreras', 'obra',
 'Avance: Toma domiciliaria La Carbonera al 78 %',
 'MC-OB-027 próxima a concluir. Verifique calidad de instalación.',
 '/backoffice/obras/MC-OB-027', 'obra', 'MC-OB-027', true,
 '2026-05-17T10:30:00+00'),

('n-mc-dag-06', 'mc-dir-agua', 'magdalena-contreras', 'alerta',
 'Resumen: 7 reportes de agua/drenaje pendientes',
 'Tiene 7 casos abiertos. 2 superan el SLA de su prioridad.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- MC-DIR-LIMPIA  ·  Arq. Jorge Vargas  (areas: limpia, comercio_vp)
-- ═══════════════════════════════════════════════════════════════════════════
('n-mc-dl-01', 'mc-dir-limpia', 'magdalena-contreras', 'alerta',
 'SLA en riesgo: Venta irregular en vía',
 'MC-RC-0384 (comercio_vp, alta prioridad) sin resolución dentro del plazo.',
 '/backoffice/reportes/MC-RC-0384', 'reporte', 'MC-RC-0384', false,
 '2026-05-20T08:35:00+00'),

('n-mc-dl-02', 'mc-dir-limpia', 'magdalena-contreras', 'reporte',
 '4 reportes nuevos de limpia hoy',
 'Ingresaron 4 reportes de recolección y limpia. Asigne rutas de cuadrilla.',
 '/backoffice/bandeja', null, null, false,
 '2026-05-20T10:15:00+00'),

('n-mc-dl-03', 'mc-dir-limpia', 'magdalena-contreras', 'cierre',
 'Cuadrilla 3 cerró tiradero clandestino',
 'Limpieza completada en zona reportada. Cascajo retirado.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-19T18:00:00+00'),

('n-mc-dl-04', 'mc-dir-limpia', 'magdalena-contreras', 'alerta',
 'Resumen: 6 reportes de limpia/comercio pendientes',
 '6 casos abiertos en sus áreas. 1 de comercio en vía pública en riesgo de SLA.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- MC-DIR-PARQUES  ·  Ing. Mariana Ortega  (areas: parques, arboles)
-- ═══════════════════════════════════════════════════════════════════════════
('n-mc-dp-01', 'mc-dir-parques', 'magdalena-contreras', 'reporte',
 'Nuevo reporte: Árbol con ramas peligrosas',
 'MC-RC-0080 requiere poda urgente en zona de conservación.',
 '/backoffice/reportes/MC-RC-0080', 'reporte', 'MC-RC-0080', false,
 '2026-05-20T09:50:00+00'),

('n-mc-dp-02', 'mc-dir-parques', 'magdalena-contreras', 'cierre',
 'Reporte resuelto: Árbol caído por viento',
 'MC-RC-0334 cerrado. Retiro de árbol completado sin incidentes.',
 '/backoffice/reportes/MC-RC-0334', 'reporte', 'MC-RC-0334', true,
 '2026-05-19T14:00:00+00'),

('n-mc-dp-03', 'mc-dir-parques', 'magdalena-contreras', 'alerta',
 '2 reportes de arbolado en riesgo de SLA',
 'Dos podas urgentes pendientes. Coordine con personal certificado.',
 '/backoffice/bandeja', null, null, false,
 '2026-05-20T08:10:00+00'),

('n-mc-dp-04', 'mc-dir-parques', 'magdalena-contreras', 'reporte',
 'Reporte: Mobiliario urbano dañado',
 'Bancas vandalizadas en parque de Lomas de San Bernabé. Solicitan reemplazo.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-18T11:30:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- MC-DIR-SEGURIDAD  ·  Mtra. Lucía Fernández  (areas: seguridad)
-- ═══════════════════════════════════════════════════════════════════════════
('n-mc-ds-01', 'mc-dir-seguridad', 'magdalena-contreras', 'cierre',
 'Caso resuelto: Vehículo abandonado',
 'MC-RC-0150 cerrado tras retiro del vehículo en coordinación con SSC-CDMX.',
 '/backoffice/reportes/MC-RC-0150', 'reporte', 'MC-RC-0150', true,
 '2026-05-19T22:00:00+00'),

('n-mc-ds-02', 'mc-dir-seguridad', 'magdalena-contreras', 'reporte',
 '2 reportes nuevos de seguridad',
 'Ingresaron 2 reportes de seguridad ciudadana en las últimas 24 h.',
 '/backoffice/bandeja', null, null, false,
 '2026-05-20T09:00:00+00'),

('n-mc-ds-03', 'mc-dir-seguridad', 'magdalena-contreras', 'alerta',
 'Alerta de Protección Civil',
 'Pronóstico de lluvias fuertes para la tarde. Activen protocolo en zonas de riesgo.',
 null, null, null, false,
 '2026-05-20T07:30:00+00'),

('n-mc-ds-04', 'mc-dir-seguridad', 'magdalena-contreras', 'alerta',
 'Resumen: 4 reportes de seguridad pendientes',
 '4 casos abiertos. 1 vandalismo, 1 vehículo, 2 riñas. Sin riesgo SLA aún.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- TL-ADMIN  ·  Gabriela Osorio Hernández
-- ═══════════════════════════════════════════════════════════════════════════
('n-tl-adm-01', 'tl-admin', 'tlalpan', 'alerta',
 'SLA en riesgo: Tablero eléctrico expuesto',
 'TL-RC-0904 (alumbrado, alta) supera tiempo de SLA. Riesgo eléctrico para peatones.',
 '/backoffice/reportes/TL-RC-0904', 'reporte', 'TL-RC-0904', false,
 '2026-05-20T09:10:00+00'),

('n-tl-adm-02', 'tl-admin', 'tlalpan', 'reporte',
 'Nuevo reporte: Tiradero clandestino',
 'TL-RC-0979 en zona de Parres el Guarda. Cascajo y residuos de construcción.',
 '/backoffice/reportes/TL-RC-0979', 'reporte', 'TL-RC-0979', false,
 '2026-05-20T10:20:00+00'),

('n-tl-adm-03', 'tl-admin', 'tlalpan', 'reporte',
 'Nuevo reporte: Fuga de agua en banqueta',
 'TL-RC-0810 reporta fuga constante. SACMEX notificado.',
 '/backoffice/reportes/TL-RC-0810', 'reporte', 'TL-RC-0810', false,
 '2026-05-20T09:45:00+00'),

('n-tl-adm-04', 'tl-admin', 'tlalpan', 'cierre',
 'Obra concluida: Pozo de absorción Bosques del Pedregal',
 'TL-OB-018 (drenaje) finalizó. Documentación de cierre entregada.',
 '/backoffice/obras/TL-OB-018', 'obra', 'TL-OB-018', true,
 '2026-05-19T17:00:00+00'),

('n-tl-adm-05', 'tl-admin', 'tlalpan', 'obra',
 'Obra en cierre: Bacheo Villa Olímpica',
 'TL-OB-046 entró en fase de cierre. Verificación final pendiente.',
 '/backoffice/obras/TL-OB-046', 'obra', 'TL-OB-046', false,
 '2026-05-20T07:00:00+00'),

('n-tl-adm-06', 'tl-admin', 'tlalpan', 'cierre',
 'Reporte resuelto: Tiradero clandestino',
 'TL-RC-0219 limpiado por Cuadrilla 3 en tiempo récord.',
 '/backoffice/reportes/TL-RC-0219', 'reporte', 'TL-RC-0219', true,
 '2026-05-19T20:00:00+00'),

('n-tl-adm-07', 'tl-admin', 'tlalpan', 'cierre',
 'Reporte resuelto: Bache de gran tamaño',
 'TL-RC-1172 reparado. Carpeta asfáltica restaurada en Av. Insurgentes Sur.',
 '/backoffice/reportes/TL-RC-1172', 'reporte', 'TL-RC-1172', true,
 '2026-05-19T15:30:00+00'),

('n-tl-adm-08', 'tl-admin', 'tlalpan', 'alerta',
 'Resumen diario: 18 reportes nuevos ayer',
 '18 reportes recibidos el 19 de mayo. 5 de prioridad alta. Revise la bandeja.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

('n-tl-adm-09', 'tl-admin', 'tlalpan', 'obra',
 'Obra en ejecución: Repavimentación Miguel Hidalgo',
 'TL-OB-028 avanza al 45 %. Sin retrasos reportados.',
 '/backoffice/obras/TL-OB-028', 'obra', 'TL-OB-028', true,
 '2026-05-18T12:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- TL-DIR-OBRAS  ·  Ing. Esteban Morales  (areas: bacheo)
-- ═══════════════════════════════════════════════════════════════════════════
('n-tl-do-01', 'tl-dir-obras', 'tlalpan', 'cierre',
 'Reporte resuelto: Bache de gran tamaño',
 'TL-RC-1172 reparado exitosamente. Cuadrilla documentó evidencia.',
 '/backoffice/reportes/TL-RC-1172', 'reporte', 'TL-RC-1172', true,
 '2026-05-19T15:30:00+00'),

('n-tl-do-02', 'tl-dir-obras', 'tlalpan', 'cierre',
 'Reporte resuelto: Bache en vialidad principal',
 'TL-RC-0118 cerrado. Reparación de carpeta completada.',
 '/backoffice/reportes/TL-RC-0118', 'reporte', 'TL-RC-0118', true,
 '2026-05-19T12:00:00+00'),

('n-tl-do-03', 'tl-dir-obras', 'tlalpan', 'obra',
 'Obra en ejecución: Bacheo Cda. Independencia',
 'TL-OB-036 avanza según programa. 3 calles afectadas.',
 '/backoffice/obras/TL-OB-036', 'obra', 'TL-OB-036', false,
 '2026-05-20T08:30:00+00'),

('n-tl-do-04', 'tl-dir-obras', 'tlalpan', 'obra',
 'Obra en cierre: Bacheo Villa Olímpica',
 'TL-OB-046 en verificación final. Revise documentación antes del acta.',
 '/backoffice/obras/TL-OB-046', 'obra', 'TL-OB-046', false,
 '2026-05-20T07:00:00+00'),

('n-tl-do-05', 'tl-dir-obras', 'tlalpan', 'alerta',
 'Resumen: 10 reportes de bacheo pendientes',
 '10 reportes abiertos. 3 en riesgo de SLA. Asigne recursos.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- TL-DIR-ALUMBRADO  ·  Ing. Sandra Juárez  (areas: alumbrado, semaforos)
-- ═══════════════════════════════════════════════════════════════════════════
('n-tl-da-01', 'tl-dir-alumbrado', 'tlalpan', 'alerta',
 'SLA en riesgo: Tablero eléctrico expuesto',
 'TL-RC-0904 supera el tiempo de respuesta. Riesgo eléctrico activo.',
 '/backoffice/reportes/TL-RC-0904', 'reporte', 'TL-RC-0904', false,
 '2026-05-20T09:10:00+00'),

('n-tl-da-02', 'tl-dir-alumbrado', 'tlalpan', 'reporte',
 'Nuevo reporte: Poste de luz parpadeante',
 'TL-RC-0572. Falla intermitente, posible cortocircuito.',
 '/backoffice/reportes/TL-RC-0572', 'reporte', 'TL-RC-0572', false,
 '2026-05-20T09:30:00+00'),

('n-tl-da-03', 'tl-dir-alumbrado', 'tlalpan', 'alerta',
 'Resumen: 6 reportes de alumbrado abiertos',
 '6 casos pendientes. 2 con riesgo de SLA. Priorice tableros expuestos.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- TL-DIR-AGUA  ·  Ing. Rafael Silva  (areas: agua, drenaje)
-- ═══════════════════════════════════════════════════════════════════════════
('n-tl-dag-01', 'tl-dir-agua', 'tlalpan', 'reporte',
 'Nuevo reporte: Fuga de agua en banqueta',
 'TL-RC-0810. Flujo constante, desperdicio de agua potable.',
 '/backoffice/reportes/TL-RC-0810', 'reporte', 'TL-RC-0810', false,
 '2026-05-20T09:45:00+00'),

('n-tl-dag-02', 'tl-dir-agua', 'tlalpan', 'cierre',
 'Obra concluida: Pozo de absorción Bosques del Pedregal',
 'TL-OB-018 cerrada. Capacidad de drenaje pluvial incrementada.',
 '/backoffice/obras/TL-OB-018', 'obra', 'TL-OB-018', true,
 '2026-05-19T17:00:00+00'),

('n-tl-dag-03', 'tl-dir-agua', 'tlalpan', 'alerta',
 'Resumen: 9 reportes de agua/drenaje abiertos',
 '9 casos pendientes en sus áreas. 3 fugas activas requieren atención.',
 '/backoffice/bandeja', null, null, false,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- TL-DIR-LIMPIA  ·  Lic. Beatriz Cárdenas  (areas: limpia, comercio_vp)
-- ═══════════════════════════════════════════════════════════════════════════
('n-tl-dl-01', 'tl-dir-limpia', 'tlalpan', 'reporte',
 'Nuevo reporte: Tiradero clandestino',
 'TL-RC-0979 en Parres el Guarda. Zona de difícil acceso.',
 '/backoffice/reportes/TL-RC-0979', 'reporte', 'TL-RC-0979', false,
 '2026-05-20T10:20:00+00'),

('n-tl-dl-02', 'tl-dir-limpia', 'tlalpan', 'reporte',
 'Nuevo reporte: Falta recolección programada',
 'TL-RC-0246 en colonia centro. Vecinos solicitan ruta extraordinaria.',
 '/backoffice/reportes/TL-RC-0246', 'reporte', 'TL-RC-0246', false,
 '2026-05-20T09:55:00+00'),

('n-tl-dl-03', 'tl-dir-limpia', 'tlalpan', 'cierre',
 'Tiradero clandestino limpiado',
 'TL-RC-0219 cerrado. 2 toneladas de cascajo retiradas.',
 '/backoffice/reportes/TL-RC-0219', 'reporte', 'TL-RC-0219', true,
 '2026-05-19T20:00:00+00'),

('n-tl-dl-04', 'tl-dir-limpia', 'tlalpan', 'alerta',
 'Resumen: 8 reportes de limpia pendientes',
 '8 casos abiertos. 2 tiraderos clandestinos y 3 fallas de recolección.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- TL-DIR-PARQUES  ·  Biól. Arturo Benítez  (areas: parques, arboles)
-- ═══════════════════════════════════════════════════════════════════════════
('n-tl-dp-01', 'tl-dir-parques', 'tlalpan', 'reporte',
 'Reporte de arbolado: poda urgente',
 'Árbol con ramas sobre cableado eléctrico en San Andrés Totoltepec.',
 '/backoffice/bandeja', null, null, false,
 '2026-05-20T09:40:00+00'),

('n-tl-dp-02', 'tl-dir-parques', 'tlalpan', 'cierre',
 'Poda preventiva completada',
 'Cuadrilla 5 realizó poda en 3 árboles de Bosques del Pedregal.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-19T16:30:00+00'),

('n-tl-dp-03', 'tl-dir-parques', 'tlalpan', 'alerta',
 'Resumen: 5 reportes de áreas verdes pendientes',
 '5 casos abiertos. 2 podas urgentes, 1 juego infantil roto.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00'),

-- ═══════════════════════════════════════════════════════════════════════════
-- TL-DIR-SEGURIDAD  ·  Mtra. Carmen López  (areas: seguridad)
-- ═══════════════════════════════════════════════════════════════════════════
('n-tl-ds-01', 'tl-dir-seguridad', 'tlalpan', 'reporte',
 '3 reportes nuevos de seguridad',
 'Ingresaron 3 reportes de seguridad ciudadana. 1 vandalismo, 2 vehículos.',
 '/backoffice/bandeja', null, null, false,
 '2026-05-20T09:15:00+00'),

('n-tl-ds-02', 'tl-dir-seguridad', 'tlalpan', 'alerta',
 'Alerta de Protección Civil',
 'Pronóstico de granizo para zona sur de Tlalpan. Activen protocolo.',
 null, null, null, false,
 '2026-05-20T07:45:00+00'),

('n-tl-ds-03', 'tl-dir-seguridad', 'tlalpan', 'cierre',
 'Vehículo abandonado retirado',
 'Coordinación con SSC-CDMX exitosa. Caso de vehículo en Lomas de Padierna cerrado.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-19T19:00:00+00'),

('n-tl-ds-04', 'tl-dir-seguridad', 'tlalpan', 'alerta',
 'Resumen: 6 reportes de seguridad pendientes',
 '6 casos abiertos. Todos dentro del SLA. Sin incidentes críticos.',
 '/backoffice/bandeja', null, null, true,
 '2026-05-20T08:00:00+00')

ON CONFLICT DO NOTHING;
