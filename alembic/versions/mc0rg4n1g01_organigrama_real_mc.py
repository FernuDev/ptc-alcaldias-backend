"""Organigrama real de la Alcaldía Magdalena Contreras (Directorio 2024-2027).

Dos cosas:
  1. Agrega la columna ``org_nodos.titular`` (persona que ocupa el puesto; solo
     display, NO una cuenta de usuario).
  2. Reconstruye el árbol organizacional del tenant ``magdalena-contreras`` con
     la estructura y los puestos REALES del directorio oficial
     (https://mcontreras.gob.mx/directorio-alcaldia-2024-2027/): Alcalde →
     Oficina de la Alcaldía + 8 Direcciones Generales → Direcciones de Área /
     Subdirecciones / Coordinaciones → JUDs / LCP / Enlaces, con su titular.

Se ejecuta como migración (no como seed) para que el organigrama real quede
reflejado en cada despliegue (Railway corre ``alembic upgrade head``). La
reconstrucción solo corre si el tenant ya existe (en una BD nueva el seed crea
la plantilla estándar; esta migración solo agrega la columna y termina).

Reasocia las cuadrillas reales (C01–C08) a la JUD correspondiente y reasigna los
usuarios demo a un nodo coherente del nuevo árbol (al borrar el árbol anterior,
``users.nodo_id`` queda en NULL por la FK ON DELETE SET NULL).
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "mc0rg4n1g01"
down_revision: str | None = "br4ndth3m01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "magdalena-contreras"

# Catálogo fijo de capacidades (por si la BD destino aún no lo tiene sembrado;
# las inserciones de nodo_capacidades necesitan que existan estos códigos).
CAPACIDADES = [
    ("proyectos", "Proyectos", 0),
    ("obras", "Obras", 1),
    ("cuadrillas", "Cuadrillas", 2),
    ("tramites", "Trámites", 3),
    ("recaudacion", "Recaudación", 4),
]


def n(nombre, nivel, tipo, titular=None, caps=None, hijos=None):
    """Helper declarativo para un nodo del árbol."""
    return {
        "nombre": nombre,
        "nivel": nivel,
        "tipo": tipo,
        "titular": titular,
        "caps": caps or {},
        "hijos": hijos or [],
    }


# ── Estructura real (children del Alcalde) ───────────────────────────────────
# nivel ∈ {alcalde, dir_general, dir_area, subdireccion, jud, lcp, enlace}
# tipo  ∈ {direccion, subdireccion, unidad}
OFICINA_ALCALDIA = [
    n("Secretaría Particular", "subdireccion", "subdireccion", "Jazmín Maqueda Chávez"),
    n(
        "Coordinación de Asesores", "subdireccion", "subdireccion",
        "Diego Pérez Villavicencio",
        hijos=[
            n('Asesor "A"', "enlace", "unidad", "Jorge Luis Aguilar Sánchez"),
            n('Asesor "B"', "enlace", "unidad", "Cristian Uriel Guijosa Méndez"),
            n('Asesor "C"', "enlace", "unidad", "Vacante"),
        ],
    ),
    n(
        "Unidad de Transparencia", "subdireccion", "subdireccion",
        "Karla Lizbeth Cárdenas Velázquez",
        hijos=[
            n("J.U.D. de Información Pública", "jud", "unidad",
              "Roberto Esteban Ballesteros Herrera"),
        ],
    ),
    n(
        "Coordinación de Comunicación Social", "subdireccion", "subdireccion",
        "Alexis Eduardo Ojeda Cabrera",
        hijos=[
            n("J.U.D. de Diseño e Imagen", "jud", "unidad", "Roland Muciño Arias"),
            n("J.U.D. de Información y Comunicación Estratégica", "jud", "unidad",
              "Héctor Iván Salazar Angulo"),
            n("Enlace de Atención a Redes Sociales", "enlace", "unidad",
              "Leonardo Isaías Cid Gallardo"),
        ],
    ),
    n(
        "Dirección de Gestión Integral de Riesgos y Protección Civil", "dir_area",
        "direccion", "Héctor Iván Nava Ramírez", caps={"cuadrillas": "usa"},
        hijos=[
            n("Subdirección de Atención a Emergencias", "subdireccion", "subdireccion",
              "Óscar Iván Ortiz Ruiz"),
            n("J.U.D. de Capacitación y Prevención", "jud", "unidad",
              "Emilio Miguel Mendoza Rodilla"),
            n("J.U.D. Operativa de Protección Civil", "jud", "unidad",
              "Tomás Zamora Plaza", caps={"cuadrillas": "usa"}),
        ],
    ),
    n(
        "Dirección de Calidad en Gobierno", "dir_area", "direccion",
        "Marco Antonio Reyes García",
        hijos=[
            n("J.U.D. de Planeación y Evaluación", "jud", "unidad", "Vacante"),
            n("J.U.D. de Implementación Normativo", "jud", "unidad",
              "Luis Alberto Lustre Orozco"),
            n("Enlace de Geografía y Estadística", "enlace", "unidad",
              "Cinthia Isabel Flores Cerón"),
            n("Enlace de Cumplimiento Normativo", "enlace", "unidad", "Vacante"),
        ],
    ),
    n(
        "Coordinación del Centro de Servicios y Atención Ciudadana (CESAC)",
        "subdireccion", "subdireccion", "Diana Alvaro Gallegos", caps={"tramites": "usa"},
        hijos=[
            n('L.C.P. de Atención Ciudadana "A"', "lcp", "unidad",
              "Balbina García Arellano"),
            n('L.C.P. de Atención Ciudadana "B"', "lcp", "unidad", "Vacante"),
            n('L.C.P. de Atención Ciudadana "C"', "lcp", "unidad", "Vacante"),
        ],
    ),
]

DIRECCIONES_GENERALES = [
    n(
        "Dirección General de Jurídico y de Gobierno", "dir_general", "direccion",
        "Jorge Muciño Arias", caps={"tramites": "central", "cuadrillas": "usa"},
        hijos=[
            n("Enlace de Apoyo", "enlace", "unidad", "Jesús Martínez Alba"),
            n("Subdirección de Ventanilla Única", "subdireccion", "subdireccion",
              "Karla Espinosa López", caps={"tramites": "usa"},
              hijos=[
                  n('L.C.P. de Ventanilla "A"', "lcp", "unidad",
                    "Antonio Sánchez Santillán"),
                  n('L.C.P. de Ventanilla "B"', "lcp", "unidad", "Vacante"),
                  n('L.C.P. de Ventanilla "C"', "lcp", "unidad",
                    "Gustavo Miguel Zepeda Hernández"),
              ]),
            n("Dirección de Asuntos Territoriales y Hábitat", "dir_area", "direccion",
              "Julio César Mendoza Jiménez",
              hijos=[
                  n("Subdirección de Hábitat y Asentamientos", "subdireccion",
                    "subdireccion", "José Javier Rubalcava Diosdado"),
                  n("J.U.D. de Supervisión de Asentamientos", "jud", "unidad",
                    "Edson Iván Esquivel Ávila"),
                  n("J.U.D. de Hábitat y Vivienda", "jud", "unidad",
                    "Christian Bassoco Chavero"),
              ]),
            n("Dirección Ejecutiva de Gobierno", "dir_area", "direccion",
              "Christian Rafael Pineda Barajas", caps={"cuadrillas": "usa"},
              hijos=[
                  n("Subdirección de Programas y Estrategias", "subdireccion",
                    "subdireccion", "Olga Rosa González Ibáñez"),
                  n("L.C.P. de Panteones", "lcp", "unidad", "Lesli Valeria Vera Rivera"),
                  n("J.U.D. de Vía Pública", "jud", "unidad", "Gerardo Rivera Zamora",
                    caps={"cuadrillas": "usa"}),
                  n("J.U.D. de Mercados y Tianguis", "jud", "unidad",
                    "Juan Gabriel Castro Guzmán"),
                  n("J.U.D. de Licencias y Control Vehicular", "jud", "unidad",
                    "Ernesto Guadalupe Partida Gutiérrez"),
              ]),
            n("Dirección de Participación Ciudadana", "dir_area", "direccion",
              "Roberto Fabián Negrete Trejo",
              hijos=[
                  n("Subdirección de Relaciones Comunitarias", "subdireccion",
                    "subdireccion", "Pamela Culver Constantino"),
                  n("L.C.P. de Enlace Participativo", "lcp", "unidad", "Vacante"),
                  n("J.U.D. de Relaciones Comunitarias y Pueblos Originarios", "jud",
                    "unidad", "Demetrio González Flores"),
                  n("J.U.D. de Control y Seguimiento al Presupuesto Participativo",
                    "jud", "unidad", "Jafeth Ernesto Rodríguez Aguilar"),
              ]),
            n("Dirección Ejecutiva de Asuntos Jurídicos", "dir_area", "direccion",
              "Alejandro Sánchez Rojas",
              hijos=[
                  n("Subdirección de Verificación Administrativa", "subdireccion",
                    "subdireccion", "Irving Aguilar Gutiérrez",
                    hijos=[
                        n('Enlace de Verificación Zona "A"', "enlace", "unidad",
                          "Marco Antonio Sánchez Rodríguez"),
                        n('Enlace de Verificación Zona "B"', "enlace", "unidad",
                          "Donovan Ballesteros Hernández"),
                        n('Enlace de Verificación Zona "C"', "enlace", "unidad",
                          "Grecia Álvarez Hernández"),
                    ]),
                  n("Coordinación de Asuntos Legales", "subdireccion", "subdireccion",
                    "Ociris Morales Vallarta"),
                  n("J.U.D. de lo Contencioso y Amparos", "jud", "unidad",
                    "Alan Misael González Jaimes"),
                  n("J.U.D. de lo Consultivo, Convenios y Derechos Humanos", "jud",
                    "unidad", "Vacante"),
                  n('J.U.D. de Calificación de Infracciones "A"', "jud", "unidad",
                    "Guadalupe Núñez Álvarez"),
                  n('J.U.D. de Calificación de Infracciones "B"', "jud", "unidad",
                    "Alejandro Argüello Jiménez"),
              ]),
        ],
    ),
    n(
        "Dirección General de Obras y Desarrollo Urbano", "dir_general", "direccion",
        "Paulina Stephania Barradas Castillo",
        caps={"obras": "central", "proyectos": "usa", "cuadrillas": "usa"},
        hijos=[
            n("Subdirección de Mantenimiento de Edificios Públicos", "subdireccion",
              "subdireccion", "Ivonne González Almaraz"),
            n("Subdirección de Control y Seguimiento Administrativo de Obras",
              "subdireccion", "subdireccion", "Wilbert Sadit Meléndez Rosales"),
            n("Subdirección de Licencias y Alineamientos", "subdireccion",
              "subdireccion", "Isaúl Moreno Gómez",
              hijos=[
                  n("J.U.D. de Manifestaciones y Licencias", "jud", "unidad",
                    "Elsa Fabiola Camacho Cruz"),
              ]),
            n("Dirección de Obras Públicas", "dir_area", "direccion",
              "Eder Alan Olivares Ramírez", caps={"obras": "central"},
              hijos=[
                  n("Subdirección Técnica", "subdireccion", "subdireccion",
                    "Elías Barrera Aguilar"),
                  n("J.U.D. de Proyectos de Obra", "jud", "unidad",
                    "Marisol Márquez González"),
                  n("J.U.D. de Concursos y Contratos", "jud", "unidad",
                    "Nohemí Sánchez Hernández"),
                  n("J.U.D. de Avance Físico-Financiero", "jud", "unidad",
                    "Fabiola Mejía Sedeño"),
                  n("Subdirección de Supervisión de Obras", "subdireccion",
                    "subdireccion", "Francisco Javier Lima Gómez",
                    hijos=[
                        n("J.U.D. de Supervisión de Edificios Públicos", "jud",
                          "unidad", "Zaira Díaz Hernández"),
                        n("J.U.D. de Supervisión de Infraestructura Urbana", "jud",
                          "unidad", "Óscar Iván García Aranda",
                          caps={"obras": "usa", "cuadrillas": "usa"}),
                    ]),
              ]),
        ],
    ),
    n(
        "Dirección General de Servicios Urbanos", "dir_general", "direccion",
        "Alfredo González Patiño", caps={"cuadrillas": "central", "proyectos": "usa"},
        hijos=[
            n("Dirección de Coordinación y Operación de Servicios Urbanos", "dir_area",
              "direccion", "José Alfredo Hernández Romero", caps={"cuadrillas": "usa"},
              hijos=[
                  n("L.C.P. de Seguimiento", "lcp", "unidad",
                    "José Abraham Rodríguez Reséndiz"),
              ]),
            n("Subdirección de Operación Hidráulica", "subdireccion", "subdireccion",
              "Oswaldo Márquez López", caps={"cuadrillas": "usa"},
              hijos=[
                  n("J.U.D. de Agua Potable", "jud", "unidad", "Daniel Sinecio Ramírez",
                    caps={"cuadrillas": "usa"}),
                  n("J.U.D. de Drenaje", "jud", "unidad", "Mario Quiroz Gaytán",
                    caps={"cuadrillas": "usa"}),
              ]),
            n("Subdirección de Conservación de Espacios Públicos", "subdireccion",
              "subdireccion", "Nadia Iracema Toledo Escobar", caps={"cuadrillas": "usa"},
              hijos=[
                  n("J.U.D. de Supervisión de Obras Viales", "jud", "unidad",
                    "Hugo Juan Sánchez Ortiz"),
                  n("J.U.D. de Alumbrado Público", "jud", "unidad",
                    "José Roberto Castro Jiménez", caps={"cuadrillas": "usa"}),
                  n("J.U.D. de Arbolado, Parques y Jardines", "jud", "unidad",
                    "Miguel Carlos Islas Rodríguez", caps={"cuadrillas": "usa"}),
              ]),
            n("Subdirección de Limpia", "subdireccion", "subdireccion",
              "Ricardo del Moral Mendoza", caps={"cuadrillas": "usa"},
              hijos=[
                  n("L.C.P. de Barrido Manual", "lcp", "unidad",
                    "Espiridión Aguilar Martínez"),
                  n("J.U.D. de Limpia", "jud", "unidad", "Javier Castro Vázquez",
                    caps={"cuadrillas": "usa"}),
              ]),
        ],
    ),
    n(
        "Dirección General de Desarrollo, Fomento Económico y Economía Circular",
        "dir_general", "direccion", "Alicia Medina Hernández",
        caps={"tramites": "usa", "recaudacion": "parcial", "proyectos": "usa"},
        hijos=[
            n("Subdirección de Turismo, Proyectos Productivos y Cooperativismo",
              "subdireccion", "subdireccion", "Yessica Acosta Ruiz",
              hijos=[
                  n("J.U.D. de Promoción Turística", "jud", "unidad",
                    "Paola Yazmín Solís Gaytán"),
                  n("J.U.D. de Productores Locales", "jud", "unidad",
                    "Eliud Guijosa Rubio"),
              ]),
            n("Subdirección de Empleo y Fomento al Comercio Local", "subdireccion",
              "subdireccion", "Beatriz Garza-Ramos Monroy",
              hijos=[
                  n("J.U.D. de Empleo y Vinculación", "jud", "unidad",
                    "Margarita Elena Hernández Landeros"),
                  n("J.U.D. de Fomento al Consumo Local", "jud", "unidad",
                    "Carlos Ignacio Mandujano Hernández"),
              ]),
            n("Subdirección de Programas Sustentables e Información Ambiental",
              "subdireccion", "subdireccion", "Onasis Galdino Zárate Paz",
              hijos=[
                  n("J.U.D. de Proyectos de Desarrollo Sustentable", "jud", "unidad",
                    "Alejandra Alvarado Torres"),
                  n("J.U.D. de Preservación de Recursos Naturales", "jud", "unidad",
                    "Tonantzin Bassoco Chavero"),
              ]),
        ],
    ),
    n(
        "Dirección General de Seguridad Ciudadana y Movilidad", "dir_general",
        "direccion", "Edgar Ariel Castro García",
        caps={"cuadrillas": "usa", "proyectos": "usa"},
        hijos=[
            n("Subdirección de Movilidad", "subdireccion", "subdireccion",
              "Carlos Gómez García",
              hijos=[
                  n("J.U.D. de Planeación de Movilidad", "jud", "unidad",
                    "Óscar Ruiz Pérez"),
                  n("J.U.D. de Vialidad y Transporte", "jud", "unidad",
                    "José David Gordillo Santana"),
              ]),
            n("Coordinación de Seguridad Ciudadana", "subdireccion", "subdireccion",
              "Wilfred Edgar Suárez Márquez", caps={"cuadrillas": "usa"},
              hijos=[
                  n("J.U.D. de Atención Ciudadana", "jud", "unidad",
                    "Pedro Alberto Gómez Olmedo"),
                  n("Subdirección de Planeación y Evaluación", "subdireccion",
                    "subdireccion", "Antonio Martínez Montes"),
                  n("J.U.D. de Monitoreo y Evaluación", "jud", "unidad",
                    "Gerardo Antonio Martínez"),
                  n("J.U.D. de Programas de Prevención", "jud", "unidad",
                    "Elvia Brenda González Ramírez"),
              ]),
        ],
    ),
    n(
        "Dirección General de Igualdad Sustantiva, Salud y Poblaciones de Atención "
        "Prioritaria", "dir_general", "direccion", "Teresa del Carmen Green Ramírez",
        caps={"proyectos": "usa", "cuadrillas": "usa"},
        hijos=[
            n("Subdirección de Atención Integral a las Mujeres", "subdireccion",
              "subdireccion", "Nelly Alicia Mejía Vega",
              hijos=[
                  n("J.U.D. de Equidad de Género", "jud", "unidad",
                    "Azucena Ordoñez del Olmo"),
                  n("J.U.D. de Empoderamiento de la Mujer", "jud", "unidad",
                    "Damaris Rodríguez González"),
              ]),
            n("Subdirección de Atención a Poblaciones Prioritarias", "subdireccion",
              "subdireccion", "Iván Reyes Moreno",
              hijos=[
                  n("J.U.D. de Atención a las Infancias", "jud", "unidad",
                    "Lluvia Rodríguez Jiménez"),
                  n("J.U.D. de Atención al Adulto Mayor y Personas con Discapacidad",
                    "jud", "unidad", "Elsy María Barillas Alcudia"),
                  n("J.U.D. de Atención a la Diversidad Sexual", "jud", "unidad",
                    "Luis Gabriel Bárcenas González"),
                  n("J.U.D. de Atención a las Juventudes", "jud", "unidad",
                    "Brisa Villagrán Salas"),
              ]),
            n("Subdirección de Servicios de Salud", "subdireccion", "subdireccion",
              "Erika Hortensia Peña Chavero",
              hijos=[
                  n("J.U.D. de Programas y Espacios Médicos", "jud", "unidad",
                    "Ramón Pichardo Jiménez"),
                  n("J.U.D. de Protección Animal", "jud", "unidad",
                    "Paola González Perales"),
              ]),
        ],
    ),
    n(
        "Dirección General de Bienestar Social", "dir_general", "direccion",
        "Edgar Omar Pineda Barajas",
        caps={"proyectos": "central", "cuadrillas": "usa", "recaudacion": "parcial"},
        hijos=[
            n("L.C.P. de Apoyo de Bienestar Social", "lcp", "unidad",
              "María Viviana Olmos Hernández"),
            n("Subdirección de Programas Sociales", "subdireccion", "subdireccion",
              "Yulyana Pérez Hernández",
              hijos=[
                  n("J.U.D. de Control, Atención y Seguimiento", "jud", "unidad",
                    "Evelyn Sánchez García"),
                  n("J.U.D. de Vinculación Comunitaria", "jud", "unidad",
                    "Elizabeth Nieto López"),
              ]),
            n("Subdirección de Educación Física y Deporte", "subdireccion",
              "subdireccion", "Arturo Contreras Bonilla",
              hijos=[
                  n("J.U.D. de Espacios Deportivos", "jud", "unidad",
                    "David Israel Vega Parra"),
                  n("J.U.D. de Promoción y Fomento al Deporte", "jud", "unidad",
                    "Hirvin David Alfaro Hernández"),
              ]),
            n("Subdirección de Cultura y Patrimonio", "subdireccion", "subdireccion",
              "Vacante",
              hijos=[
                  n("J.U.D. de Patrimonio y Recintos Culturales", "jud", "unidad",
                    "Israel Sánchez Pérez"),
                  n("J.U.D. de Promoción Cultural", "jud", "unidad",
                    "Rodrigo Pérez Olvera"),
              ]),
        ],
    ),
    n(
        "Dirección General de Administración y Finanzas", "dir_general", "direccion",
        "Francisco Javier Castro Hernández",
        caps={"recaudacion": "central", "proyectos": "usa"},
        hijos=[
            n("J.U.D. de Gestión Administrativa", "jud", "unidad",
              "Rocío Verenice Galicia Godínez",
              hijos=[
                  n("Enlace de Gestión Administrativa", "enlace", "unidad",
                    "Helena Rojas Romero"),
              ]),
            n("J.U.D. de Atención y Seguimiento de Auditorías", "jud", "unidad",
              "Gisela Landa Lara"),
            n("Subdirección de Alcaldía Digital", "subdireccion", "subdireccion",
              "Vacante",
              hijos=[
                  n("J.U.D. de Soporte Técnico y Comunicación", "jud", "unidad",
                    "Aide Ortiz Acosta"),
                  n("J.U.D. de Sistemas", "jud", "unidad", "Gilberto Flores"),
                  n("J.U.D. de Gobierno Electrónico", "jud", "unidad",
                    "Ariadna Cruz Hernández"),
              ]),
            n("Dirección de Finanzas y Administración de Capital Humano", "dir_area",
              "direccion", "Danae Álvarez Fombona", caps={"recaudacion": "usa"},
              hijos=[
                  n("Subdirección de Finanzas", "subdireccion", "subdireccion",
                    "Gerardo Nieto García",
                    hijos=[
                        n("J.U.D. de Contabilidad", "jud", "unidad",
                          "Ramiro Arzate Castro"),
                        n("J.U.D. de Autogenerados", "jud", "unidad",
                          "Karla Gabriela Prado Martínez"),
                        n("J.U.D. de Tesorería", "jud", "unidad",
                          "Dolores Sabrina Durán Rodríguez"),
                        n("J.U.D. de Evaluación e Integración Presupuestal", "jud",
                          "unidad", "Claudio Francisco Bistrain Belmont"),
                    ]),
                  n("Subdirección de Administración de Capital Humano", "subdireccion",
                    "subdireccion", "Fernando Hidalgo Valtierra",
                    hijos=[
                        n("J.U.D. de Relaciones Laborales y Prestaciones", "jud",
                          "unidad", "Blanca Viridiana Vázquez Aguilar"),
                        n("J.U.D. de Nóminas y Pagos", "jud", "unidad",
                          "Brenda Karen Lagunas Rangel"),
                        n("J.U.D. de Planeación, Registros y Movimientos", "jud",
                          "unidad", "Yolox Mallinali Maldonado Guzmán"),
                    ]),
              ]),
            n("Dirección de Recursos Materiales, Abastecimientos y Servicios",
              "dir_area", "direccion", "Alfredo Adbeel Bustamante Rocha",
              hijos=[
                  n("Subdirección de Adquisiciones y Abastecimientos", "subdireccion",
                    "subdireccion", "Mónica Margarita Jaracuaro Ochoa",
                    hijos=[
                        n("J.U.D. de Adquisiciones", "jud", "unidad",
                          "Itzayana Cruz Hernández"),
                        n("J.U.D. de Almacenes e Inventarios", "jud", "unidad",
                          "Sergio Salvador Sánchez Caballero Rigalt"),
                    ]),
                  n("Subdirección de Servicios Generales", "subdireccion",
                    "subdireccion", "Ismael Carmona Hernández",
                    hijos=[
                        n("J.U.D. de Mantenimiento del Parque Vehicular", "jud",
                          "unidad", "Sergio Gallegos Juárez"),
                        n("J.U.D. de Apoyo de Servicios Generales", "jud", "unidad",
                          "Felipe Espinoza Murguía"),
                        n("J.U.D. de Apoyos Logísticos", "jud", "unidad",
                          "José Ángel Rivera Guerrero"),
                    ]),
              ]),
        ],
    ),
]

# Cuadrilla (id) -> JUD destino (nombre único en el árbol). El nodo de la
# cuadrilla cuelga de esa JUD con su cuadrilla_id (la vista de Personal le
# adjunta integrantes/jefe).
CUADRILLA_DESTINO = {
    "C01": "J.U.D. de Supervisión de Infraestructura Urbana",
    "C02": "J.U.D. de Alumbrado Público",
    "C03": "J.U.D. de Limpia",
    "C04": "J.U.D. de Agua Potable",
    "C05": "J.U.D. de Arbolado, Parques y Jardines",
    "C06": "J.U.D. de Vía Pública",
    "C07": "J.U.D. Operativa de Protección Civil",
    "C08": "J.U.D. de Drenaje",
}

# Usuario demo (id) -> nodo destino (nombre único). Reasigna su posición tras
# reconstruir el árbol (al borrar el anterior, su nodo_id quedó NULL).
USUARIO_NODO = {
    "mc-admin": "Alcalde",
    "mc-dir-obras": "Dirección General de Obras y Desarrollo Urbano",
    "mc-dir-agua": "Subdirección de Operación Hidráulica",
    "mc-dir-alumbrado": "J.U.D. de Alumbrado Público",
    "mc-dir-parques": "J.U.D. de Arbolado, Parques y Jardines",
    "mc-dir-limpia": "Subdirección de Limpia",
    "mc-dir-seguridad": "Dirección General de Seguridad Ciudadana y Movilidad",
    "mc-supervisor": "Coordinación del Centro de Servicios y Atención Ciudadana (CESAC)",
    "mc-inspector": "Subdirección de Verificación Administrativa",
}


def _insert_tree(conn, parent_id, nodos, name_to_id):
    """Inserta recursivamente la lista de nodos bajo parent_id."""
    for orden, nodo in enumerate(nodos):
        nid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO org_nodos
                    (id, tenant_id, parent_id, nivel, tipo, nombre, titular,
                     orden, activo, cuadrilla_id, created_at, updated_at)
                VALUES
                    (:id, :tenant, :parent, :nivel, :tipo, :nombre, :titular,
                     :orden, true, NULL, now(), now())
                """
            ),
            {
                "id": nid,
                "tenant": TENANT,
                "parent": parent_id,
                "nivel": nodo["nivel"],
                "tipo": nodo["tipo"],
                "nombre": nodo["nombre"],
                "titular": nodo["titular"],
                "orden": orden,
            },
        )
        # El último gana en caso de nombres repetidos; solo consultamos nombres
        # únicos (direcciones, subdirecciones de operación, JUDs destino).
        name_to_id[nodo["nombre"]] = nid
        for cod, niv in nodo["caps"].items():
            conn.execute(
                sa.text(
                    "INSERT INTO nodo_capacidades (nodo_id, capacidad, nivel_uso) "
                    "VALUES (:nodo, :cap, :niv)"
                ),
                {"nodo": nid, "cap": cod, "niv": niv},
            )
        if nodo["hijos"]:
            _insert_tree(conn, nid, nodo["hijos"], name_to_id)


def upgrade() -> None:
    op.add_column("org_nodos", sa.Column("titular", sa.String(length=160), nullable=True))

    conn = op.get_bind()

    # Solo reconstruimos si el tenant ya existe (BD ya sembrada). En una BD nueva
    # el seed crea la plantilla estándar; aquí solo dejamos la columna.
    exists = conn.execute(
        sa.text("SELECT 1 FROM tenants WHERE id = :t"), {"t": TENANT}
    ).first()
    if not exists:
        return

    # Catálogo de capacidades (idempotente) para satisfacer las FK.
    for cod, nombre, orden in CAPACIDADES:
        conn.execute(
            sa.text(
                "INSERT INTO capacidades (codigo, nombre, orden) "
                "VALUES (:c, :n, :o) ON CONFLICT (codigo) DO NOTHING"
            ),
            {"c": cod, "n": nombre, "o": orden},
        )

    # Borrar el árbol anterior del tenant (cascada a hijos y nodo_capacidades;
    # users.nodo_id -> NULL por ON DELETE SET NULL).
    conn.execute(
        sa.text("DELETE FROM org_nodos WHERE tenant_id = :t"), {"t": TENANT}
    )

    name_to_id: dict[str, str] = {}

    # Raíz: Alcalde.
    alcalde_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            """
            INSERT INTO org_nodos
                (id, tenant_id, parent_id, nivel, tipo, nombre, titular,
                 orden, activo, cuadrilla_id, created_at, updated_at)
            VALUES
                (:id, :t, NULL, 'alcalde', 'direccion', 'Alcalde', :titular,
                 0, true, NULL, now(), now())
            """
        ),
        {"id": alcalde_id, "t": TENANT, "titular": "José Fernando Mercado Guaida"},
    )
    name_to_id["Alcalde"] = alcalde_id

    # Oficina de la Alcaldía + Direcciones Generales bajo el Alcalde.
    _insert_tree(conn, alcalde_id, OFICINA_ALCALDIA + DIRECCIONES_GENERALES, name_to_id)

    # Reasociar las cuadrillas reales del tenant a su JUD destino.
    cuadrillas = conn.execute(
        sa.text("SELECT id, nombre FROM cuadrillas WHERE tenant_id = :t"),
        {"t": TENANT},
    ).fetchall()
    cuad_by_id = {row[0]: row[1] for row in cuadrillas}
    for cuad_id, jud_nombre in CUADRILLA_DESTINO.items():
        if cuad_id not in cuad_by_id:
            continue  # esa cuadrilla no existe en esta BD
        jud_id = name_to_id.get(jud_nombre)
        if jud_id is None:
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO org_nodos
                    (id, tenant_id, parent_id, nivel, tipo, nombre, titular,
                     orden, activo, cuadrilla_id, created_at, updated_at)
                VALUES
                    (:id, :t, :parent, 'jefe_cuadrilla', 'cuadrilla', :nombre, NULL,
                     0, true, :cuad, now(), now())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "t": TENANT,
                "parent": jud_id,
                "nombre": cuad_by_id[cuad_id],
                "cuad": cuad_id,
            },
        )

    # Reasignar usuarios demo a un nodo coherente (su nodo_id quedó NULL al borrar).
    for user_id, nodo_nombre in USUARIO_NODO.items():
        nodo_id = name_to_id.get(nodo_nombre)
        if nodo_id is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE users SET nodo_id = :nodo, es_campo = false "
                "WHERE id = :uid AND tenant_id = :t"
            ),
            {"nodo": nodo_id, "uid": user_id, "t": TENANT},
        )


def downgrade() -> None:
    op.drop_column("org_nodos", "titular")
