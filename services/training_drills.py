"""A suggested training exercise for each kind of possible tactical issue.

The AI detects the issue; it does not invent the exercise. This is a fixed catalogue, written by the
team from common coaching practice: one exercise per issue code of the AI service (tactical_insights.py),
so the coach has a concrete starting point to work on what the video showed. Sizes, numbers and times
are a guide for an adult team and must be adapted to the category.

The stored possible issues keep the AI's title, not its code, so the titles of the AI rules are mapped
to their code here (14 titles, 12 codes).
"""

from __future__ import annotations

from typing import TypedDict


class Drill(TypedDict):
    name: str
    objective: str
    organization: str
    development: str
    keys: list[str]
    variant: str


NOTE = ("Ejercicio sugerido como guía de trabajo, no calculado por la IA: ajusta el espacio, el número de "
        "jugadores y los tiempos a tu categoría.")

DRILLS: dict[str, Drill] = {
    "EXCESSIVE_DISTANCE_BETWEEN_LINES": {
        "name": "Bloque en acordeón",
        "objective": "Que la defensa y el mediocampo se muevan juntos y no dejen espacio entre líneas.",
        "organization": "Medio campo. 4 defensores y 4 mediocampistas contra 6 atacantes y un comodín. Conos que "
                        "marcan una franja de 12 a 15 m que debe separar, como máximo, la defensa del mediocampo. "
                        "4 series de 5 minutos.",
        "development": "Los atacantes mueven el balón buscando recibir entre líneas. Cuando el balón va hacia atrás, "
                       "la defensa sube con el mediocampo; cuando el rival puede jugar al espacio, bajan juntos. "
                       "Cada recepción de un atacante entre las dos líneas es un punto para los atacantes.",
        "keys": ["La defensa sube cuando el balón va atrás o el poseedor está presionado.",
                 "El mediocampo no salta a presionar sin que la defensa acompañe.",
                 "El central da la voz para subir y bajar."],
        "variant": "Limitar a los atacantes a dos toques para que el balón circule más rápido.",
    },
    "LOW_TEAM_COMPACTNESS": {
        "name": "Partido en dos franjas",
        "objective": "Defender en un bloque corto y estrecho, cerca del balón.",
        "organization": "Cancha de 60 × 45 m dividida en tres franjas a lo ancho. 8 contra 8 con porteros. "
                        "4 series de 6 minutos.",
        "development": "Partido normal con una regla: el equipo que defiende debe tener a todos sus jugadores de campo "
                       "en dos franjas seguidas como máximo. Si un defensor queda en la tercera franja, el rival "
                       "suma un punto.",
        "keys": ["Bascular hacia el lado del balón.", "Al perder el balón, acortar y cerrar el centro.",
                 "Distancias cortas entre compañeros de la misma línea."],
        "variant": "Reducir el bloque permitido a una franja y media.",
    },
    "EXCESSIVE_SPACING": {
        "name": "Rondo 4 contra 2 con pareja unida",
        "objective": "Mantener apoyos y coberturas a distancia corta entre jugadores cercanos.",
        "organization": "Cuadrado de 10 × 10 m. 4 jugadores con balón contra 2 defensores. Series de 2 minutos, "
                        "cambiando defensores.",
        "development": "Los cuatro de fuera se pasan el balón a uno o dos toques. Los dos defensores presionan juntos: "
                       "uno sale al poseedor y el otro cubre el pase por dentro, sin separarse más de 4 o 5 m. "
                       "Si recuperan, cambian con quien perdió el balón.",
        "keys": ["El que no presiona cubre a su compañero.", "Los apoyos se ofrecen cerca y en ángulo.",
                 "Hablar para no ir los dos al mismo jugador."],
        "variant": "5 contra 2 en 12 × 12 m, con un pase entre los dos defensores que vale un punto si se corta.",
    },
    "DEFENSIVE_LINE_TOO_DEEP": {
        "name": "Línea de cuatro que sube",
        "objective": "Que la línea defensiva sepa cuándo subir para no quedar hundida cerca del área.",
        "organization": "Desde el medio campo hasta la portería. Portero y 4 defensores contra 4 atacantes, con 2 "
                        "mediocampistas que les sirven el balón. Línea de conos a 25 m de la portería. "
                        "Series de 5 ataques.",
        "development": "Cuando el balón va hacia atrás o el poseedor está presionado, la línea sube junta hasta los "
                       "conos; cuando el poseedor tiene tiempo para el pase largo, baja. Se juega con fuera de lugar.",
        "keys": ["Subir con el balón cubierto, bajar con el balón descubierto.",
                 "Los cuatro a la misma altura, mirando al central.",
                 "Subir rápido y juntos, no de uno en uno."],
        "variant": "Agregar un mediocampista defensor que presione al poseedor.",
    },
    "HIGH_ZONE_CONCENTRATION": {
        "name": "Partido con zonas limitadas",
        "objective": "Ocupar la cancha de forma equilibrada en vez de amontonarse cerca del balón.",
        "organization": "Cancha de 60 × 45 m dividida en 6 zonas (3 a lo largo × 2 a lo ancho). 7 contra 7 con "
                        "porteros. 4 series de 6 minutos.",
        "development": "Partido normal con una regla: nunca puede haber más de 3 jugadores del mismo equipo en una "
                       "zona. Si pasa, es falta para el rival.",
        "keys": ["Quien no participa en la jugada equilibra el lado contrario.",
                 "Formar triángulos entre zonas vecinas.", "Mirar antes de recibir dónde hay espacio libre."],
        "variant": "Bajar el límite a 2 jugadores por zona.",
    },
    "INSUFFICIENT_WIDTH": {
        "name": "Partido con bandas libres",
        "objective": "Abrir la cancha cuando el equipo tiene el balón.",
        "organization": "Cancha de 60 × 45 m con dos pasillos laterales de 8 m. 6 contra 6 dentro y un jugador por "
                        "equipo en cada pasillo, donde nadie lo puede presionar. 4 series de 6 minutos.",
        "development": "Los jugadores de banda juegan pegados a la línea. El gol que llega después de un pase desde "
                       "una banda vale doble.",
        "keys": ["Los extremos abiertos, con los pies cerca de la línea.",
                 "Mover el balón de un lado a otro para abrir espacios por dentro.",
                 "El lateral sube cuando el extremo se mete por dentro."],
        "variant": "Permitir que un defensor entre al pasillo para presionar al de banda.",
    },
    "NUMERICAL_IMBALANCE": {
        "name": "Partido por sectores con jugador libre",
        "objective": "Igualar o superar en número al rival en la zona del balón.",
        "organization": "Cancha de 60 × 45 m dividida en 3 pasillos a lo largo. 2 contra 2 fijos en cada pasillo y un "
                        "jugador libre por equipo que puede cambiar de pasillo. 4 series de 6 minutos.",
        "development": "El jugador libre se mueve al pasillo del balón para formar un 3 contra 2 cuando su equipo "
                       "ataca, o para igualar a 3 contra 3 cuando defiende.",
        "keys": ["Leer dónde está el balón antes de moverse.",
                 "Llegar a tiempo, no antes: si llega pronto, el rival se reorganiza.",
                 "Al defender, el más cercano cierra el pasillo del balón."],
        "variant": "Dos jugadores libres por equipo.",
    },
    "DISCONNECTED_TEAM": {
        "name": "Salida por tres zonas",
        "objective": "Mantener conectadas defensa, mediocampo y ataque para que el balón pase de una línea a otra.",
        "organization": "Dos tercios de cancha divididos en 3 zonas: salida, medio y ataque. 9 contra 6. "
                        "Series de 8 minutos.",
        "development": "El equipo de 9 sale jugando desde el portero y debe pasar el balón por las tres zonas sin "
                       "saltarse la del medio. Si una línea queda sin un compañero al que pasar en la zona siguiente, "
                       "la jugada se reinicia.",
        "keys": ["Siempre debe haber alguien para recibir en la zona siguiente.",
                 "Los mediocampistas se ofrecen entre las líneas rivales.",
                 "Cuando el balón avanza, la línea de atrás acompaña."],
        "variant": "Igualar a 9 contra 8 para aumentar la presión.",
    },
    "ISOLATED_PLAYERS": {
        "name": "Triángulos en movimiento",
        "objective": "Que cada jugador tenga siempre un compañero cerca para pasar o recibir.",
        "organization": "Cancha de 40 × 30 m. Grupos de 3 jugadores con un balón contra 2 defensores. "
                        "Series de 3 minutos.",
        "development": "Cada grupo avanza de una línea a la otra pasándose el balón sin dejar de formar un triángulo. "
                       "Los defensores intentan cortar los pases. Un jugador solo, sin compañero a pocos metros, "
                       "es un pase perdido.",
        "keys": ["Moverse después de pasar para dar otra línea de pase.",
                 "Ofrecerse en diagonal, no en línea recta.", "Ajustar la distancia según la presión."],
        "variant": "Grupos de 4 contra 3 defensores.",
    },
    "LOW_BALL_PRESSURE": {
        "name": "Presión tras pérdida de 5 segundos",
        "objective": "Presionar al poseedor justo después de perder el balón.",
        "organization": "Cancha de 40 × 30 m. 6 contra 6 con 2 comodines que juegan con quien tiene el balón. "
                        "4 series de 4 minutos.",
        "development": "Juego de posesión. Cuando un equipo pierde el balón tiene 5 segundos para recuperarlo: si lo "
                       "logra, suma un punto. El rival suma un punto cada 6 pases seguidos.",
        "keys": ["El más cercano sale de inmediato al poseedor.",
                 "Orientar la presión hacia la banda.", "Los demás cierran los pases cortos."],
        "variant": "Bajar a 3 segundos para recuperar.",
    },
    "NARROW_ATTACK": {
        "name": "Cambio de orientación",
        "objective": "Atacar usando todo el ancho y cambiar el balón de lado.",
        "organization": "Medio campo con dos porterías. 6 atacantes contra 4 defensores y portero. Conos que marcan "
                        "dos carriles laterales. Series de 6 ataques.",
        "development": "El gol solo vale si antes el balón pasó por los dos carriles laterales, de uno al otro, en "
                       "menos de 4 pases.",
        "keys": ["Abrir el juego antes de que el rival bascule.",
                 "Pase largo al lado débil o circulación rápida por dentro.", "El jugador del lado contrario abierto y esperando."],
        "variant": "Que el gol después de un cambio de orientación de un solo pase valga doble.",
    },
    "NO_ATTACKING_DEPTH": {
        "name": "Desmarque de ruptura",
        "objective": "Tener jugadores por delante del balón que ataquen la espalda de la defensa.",
        "organization": "Último tercio de cancha. 4 atacantes contra 3 defensores y portero. Series de 6 ataques.",
        "development": "El ataque debe tener siempre al menos un jugador por delante de la línea del balón. El gol que "
                       "llega después de un pase a la espalda de la defensa vale doble.",
        "keys": ["Romper en el momento en que el poseedor levanta la cabeza.",
                 "Arrancar en diagonal para no quedar en fuera de lugar.", "Un jugador fija a la defensa y otro rompe."],
        "variant": "Agregar un defensor que llega desde atrás para cerrar el espacio.",
    },
}

# Titles of the AI rules (tactical_insights.py) -> issue code. Several titles share a code.
TITLE_TO_CODE = {
    "Posible problema táctico: distancia excesiva entre la línea defensiva y el mediocampo": "EXCESSIVE_DISTANCE_BETWEEN_LINES",
    "Posible problema táctico: distancia excesiva entre las líneas del equipo": "EXCESSIVE_DISTANCE_BETWEEN_LINES",
    "Posible problema táctico: baja compactación del equipo": "LOW_TEAM_COMPACTNESS",
    "Posible problema táctico: distancia promedio grande entre compañeros": "LOW_TEAM_COMPACTNESS",
    "Posible problema táctico: separación excesiva entre jugadores cercanos": "EXCESSIVE_SPACING",
    "Posible problema táctico: línea defensiva demasiado retrasada": "DEFENSIVE_LINE_TOO_DEEP",
    "Posible problema táctico: alta concentración de jugadores en una zona": "HIGH_ZONE_CONCENTRATION",
    "Posible problema táctico: amplitud insuficiente": "INSUFFICIENT_WIDTH",
    "Posible problema táctico: desequilibrio numérico en una zona": "NUMERICAL_IMBALANCE",
    "Posible problema táctico: equipo partido en grupos sin conexión": "DISCONNECTED_TEAM",
    "Posible problema táctico: jugadores sin apoyo cercano": "ISOLATED_PLAYERS",
    "Posible problema táctico: poca presión sobre el balón": "LOW_BALL_PRESSURE",
    "Posible problema táctico: ataque demasiado estrecho": "NARROW_ATTACK",
    "Posible problema táctico: falta de profundidad en ataque": "NO_ATTACKING_DEPTH",
}


def drill_for(title: str) -> dict | None:
    """The suggested exercise of a stored possible issue (by its title), with the note on how to use it."""
    code = TITLE_TO_CODE.get(title.strip())
    if code is None:
        return None
    return {"code": code, **DRILLS[code], "note": NOTE}
