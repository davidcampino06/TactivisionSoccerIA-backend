"""A suggested training exercise for each kind of possible tactical issue.

The AI detects the issue; it does not invent the exercise. This is a fixed catalogue, written by the
team from common coaching practice: exercises per issue code of the AI service (tactical_insights.py),
so the coach has a concrete starting point to work on what the video showed. Each code has three
exercises: a main one and two alternatives, so the work can change from one week to the next. Sizes, numbers and times
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

# Three exercises per issue code: the first is the main one; the others are alternatives to vary the work.
DRILLS: dict[str, list[Drill]] = {
    "EXCESSIVE_DISTANCE_BETWEEN_LINES": [
        {
            "name": "Bloque en acordeón",
            "objective": "Que la defensa y el mediocampo se muevan juntos y no dejen espacio entre líneas.",
            "organization": "Medio campo. 4 defensores y 4 mediocampistas contra 6 atacantes y un comodín. Conos que marcan una franja de 12 a 15 m que debe separar, como máximo, la defensa del mediocampo. 4 series de 5 minutos.",
            "development": "Los atacantes mueven el balón buscando recibir entre líneas. Cuando el balón va hacia atrás, la defensa sube con el mediocampo; cuando el rival puede jugar al espacio, bajan juntos. Cada recepción de un atacante entre las dos líneas es un punto para los atacantes.",
            "keys": [
                "La defensa sube cuando el balón va atrás o el poseedor está presionado.",
                "El mediocampo no salta a presionar sin que la defensa acompañe.",
                "El central da la voz para subir y bajar.",
            ],
            "variant": "Limitar a los atacantes a dos toques para que el balón circule más rápido.",
        },
        {
            "name": "Cerrar el espacio entre líneas",
            "objective": "Que nadie del rival reciba cómodo entre la defensa y el mediocampo.",
            "organization": "Medio campo. 4 defensores y 2 mediocentros contra 5 atacantes y un receptor que solo se mueve en una franja de 10 m entre las dos líneas. 4 series de 4 minutos.",
            "development": "Los atacantes buscan pasarle el balón al receptor de la franja. Cada pase que recibe es un punto. Defensa y mediocentros acortan para dejarlo sin espacio: la defensa sube y los mediocentros bajan.",
            "keys": [
                "El mediocentro mira dónde está el receptor antes de salir a presionar.",
                "El central que sale a la franja vuelve en cuanto el balón se va.",
                "Acortar sin dejar la espalda libre: subir solo con el balón cubierto.",
            ],
            "variant": "Dos receptores en la franja.",
        },
        {
            "name": "Partido con fuera de lugar adelantado",
            "objective": "Jugar con la defensa más alta y pegada al mediocampo.",
            "organization": "Cancha de 70 × 50 m con porteros. 8 contra 8. Una línea de conos a 25 m de cada portería. 3 series de 8 minutos.",
            "development": "Partido normal, pero el fuera de lugar se marca desde la línea de conos y no desde el último defensor. La defensa puede jugar por delante de los conos y el mediocampo tiene que acompañarla.",
            "keys": [
                "La línea defensiva se adelanta junta.",
                "El mediocampo ocupa el espacio que deja la defensa al subir.",
                "El portero cubre la espalda de la defensa.",
            ],
            "variant": "Correr la línea de conos a 30 m.",
        },
    ],
    "LOW_TEAM_COMPACTNESS": [
        {
            "name": "Partido en dos franjas",
            "objective": "Defender en un bloque corto y estrecho, cerca del balón.",
            "organization": "Cancha de 60 × 45 m dividida en tres franjas a lo ancho. 8 contra 8 con porteros. 4 series de 6 minutos.",
            "development": "Partido normal con una regla: el equipo que defiende debe tener a todos sus jugadores de campo en dos franjas seguidas como máximo. Si un defensor queda en la tercera franja, el rival suma un punto.",
            "keys": [
                "Bascular hacia el lado del balón.",
                "Al perder el balón, acortar y cerrar el centro.",
                "Distancias cortas entre compañeros de la misma línea.",
            ],
            "variant": "Reducir el bloque permitido a una franja y media.",
        },
        {
            "name": "Basculación contra tres porterías",
            "objective": "Que el bloque se desplace junto hacia el lado del balón.",
            "organization": "Cancha de 50 × 40 m con tres porterías pequeñas en una línea de fondo. 6 defensores contra 8 atacantes. Series de 4 minutos.",
            "development": "Los atacantes mueven el balón de lado a lado y pueden marcar en cualquiera de las tres porterías. Los defensores no pueden cubrir las tres a la vez: tienen que bascular juntos hacia el lado del balón.",
            "keys": [
                "Toda la línea se mueve a la vez, no solo el que está cerca del balón.",
                "El lado contrario al balón se cierra hacia el centro.",
                "Cambiar de lado rápido cuando el rival cambia la orientación.",
            ],
            "variant": "Permitir a los atacantes cambiar de lado con un solo pase largo.",
        },
        {
            "name": "Bloque en sombra",
            "objective": "Aprender las distancias del bloque según dónde está el balón.",
            "organization": "Media cancha con el sistema del equipo (10 jugadores) y 8 marcas en el piso. Sin rival. 10 minutos.",
            "development": "El entrenador pone el balón en una de las marcas y el equipo se coloca como si defendiera esa jugada, sin correr. Se corrigen las distancias y se cambia el balón de marca. Después se repite con un rival que mueve el balón.",
            "keys": [
                "Las distancias entre líneas no cambian aunque el balón se mueva.",
                "Cada jugador mira el balón y a su compañero más cercano.",
                "Primero despacio y bien; después a ritmo de partido.",
            ],
            "variant": "Agregar 6 atacantes que mueven el balón entre las marcas.",
        },
    ],
    "EXCESSIVE_SPACING": [
        {
            "name": "Rondo 4 contra 2 con pareja unida",
            "objective": "Mantener apoyos y coberturas a distancia corta entre jugadores cercanos.",
            "organization": "Cuadrado de 10 × 10 m. 4 jugadores con balón contra 2 defensores. Series de 2 minutos, cambiando defensores.",
            "development": "Los cuatro de fuera se pasan el balón a uno o dos toques. Los dos defensores presionan juntos: uno sale al poseedor y el otro cubre el pase por dentro, sin separarse más de 4 o 5 m. Si recuperan, cambian con quien perdió el balón.",
            "keys": [
                "El que no presiona cubre a su compañero.",
                "Los apoyos se ofrecen cerca y en ángulo.",
                "Hablar para no ir los dos al mismo jugador.",
            ],
            "variant": "5 contra 2 en 12 × 12 m, con un pase entre los dos defensores que vale un punto si se corta.",
        },
        {
            "name": "Defensa en parejas 2 contra 2",
            "objective": "Que dos defensores cercanos se cubran sin separarse.",
            "organization": "Cancha de 20 × 15 m con dos porterías pequeñas. Parejas 2 contra 2. Series de 90 segundos.",
            "development": "Los atacantes intentan marcar en las porterías pequeñas. Los defensores trabajan juntos: uno presiona al poseedor y el otro lo cubre en diagonal, a pocos metros.",
            "keys": [
                "Cobertura en diagonal, nunca en la misma línea.",
                "Cambiar los papeles cuando el balón pasa al otro atacante.",
                "Hablar: «salgo» y «cubro».",
            ],
            "variant": "3 contra 3 en 30 × 20 m.",
        },
        {
            "name": "Posesión en espacio reducido",
            "objective": "Acostumbrar al equipo a jugar con apoyos cortos.",
            "organization": "Cuadrado de 25 × 20 m. 5 contra 5 y un comodín. Series de 3 minutos.",
            "development": "Juego de posesión a dos toques. Cada 8 pases seguidos es un punto. El espacio pequeño obliga a ofrecer apoyos cerca y a cubrir a corta distancia al defender.",
            "keys": [
                "Ofrecerse cerca y en ángulo, no detrás del rival.",
                "Al perder el balón, presionar de inmediato con el más cercano.",
                "Separarse solo lo necesario para recibir.",
            ],
            "variant": "Un solo toque para el comodín.",
        },
    ],
    "DEFENSIVE_LINE_TOO_DEEP": [
        {
            "name": "Línea de cuatro que sube",
            "objective": "Que la línea defensiva sepa cuándo subir para no quedar hundida cerca del área.",
            "organization": "Desde el medio campo hasta la portería. Portero y 4 defensores contra 4 atacantes, con 2 mediocampistas que les sirven el balón. Línea de conos a 25 m de la portería. Series de 5 ataques.",
            "development": "Cuando el balón va hacia atrás o el poseedor está presionado, la línea sube junta hasta los conos; cuando el poseedor tiene tiempo para el pase largo, baja. Se juega con fuera de lugar.",
            "keys": [
                "Subir con el balón cubierto, bajar con el balón descubierto.",
                "Los cuatro a la misma altura, mirando al central.",
                "Subir rápido y juntos, no de uno en uno.",
            ],
            "variant": "Agregar un mediocampista defensor que presione al poseedor.",
        },
        {
            "name": "Subir al pase atrás",
            "objective": "Que la línea defensiva gane metros cada vez que el balón va hacia atrás.",
            "organization": "Media cancha. Portero y 4 defensores contra 2 delanteros. Dos mediocampistas que pasan el balón. Series de 5 minutos.",
            "development": "Los mediocampistas se pasan el balón. Cada pase hacia atrás, la línea sube unos metros; cuando un mediocampista levanta la cabeza para el pase largo, la línea se frena y retrocede. Los delanteros buscan la espalda de la defensa.",
            "keys": [
                "Subir mientras el balón viaja, no cuando ya llegó.",
                "Frenar y retroceder cuando el poseedor está libre.",
                "El portero ajusta su posición con la línea.",
            ],
            "variant": "Los delanteros pueden bajar a recibir y el central decide si los sigue.",
        },
        {
            "name": "Partido con zona prohibida delante del área",
            "objective": "Evitar que la defensa se quede hundida mientras el balón está lejos.",
            "organization": "Cancha de 70 × 50 m con porteros. 8 contra 8. Una franja de 10 m delante de cada área marcada con conos. 3 series de 8 minutos.",
            "development": "Mientras el balón está en la mitad rival, ningún defensor puede quedarse en la franja de su propia área: si alguno está ahí, el rival suma un punto. Cuando el balón entra en la propia mitad, la defensa puede bajar.",
            "keys": [
                "Subir cuando el equipo ataca.",
                "Bajar a tiempo cuando el rival recupera el balón.",
                "Moverse en línea, no uno por uno.",
            ],
            "variant": "Agrandar la franja a 15 m.",
        },
    ],
    "HIGH_ZONE_CONCENTRATION": [
        {
            "name": "Partido con zonas limitadas",
            "objective": "Ocupar la cancha de forma equilibrada en vez de amontonarse cerca del balón.",
            "organization": "Cancha de 60 × 45 m dividida en 6 zonas (3 a lo largo × 2 a lo ancho). 7 contra 7 con porteros. 4 series de 6 minutos.",
            "development": "Partido normal con una regla: nunca puede haber más de 3 jugadores del mismo equipo en una zona. Si pasa, es falta para el rival.",
            "keys": [
                "Quien no participa en la jugada equilibra el lado contrario.",
                "Formar triángulos entre zonas vecinas.",
                "Mirar antes de recibir dónde hay espacio libre.",
            ],
            "variant": "Bajar el límite a 2 jugadores por zona.",
        },
        {
            "name": "Rondo de dos cuadrados",
            "objective": "No amontonarse junto al balón y cambiar el juego a la zona libre.",
            "organization": "Dos cuadrados de 15 × 15 m separados por 10 m. Equipo de 8 (4 en cada cuadrado) contra 3 defensores. Series de 3 minutos.",
            "development": "Los 4 del cuadrado con balón lo mantienen contra los defensores. Después de 5 pases deben cambiarlo al otro cuadrado, y los defensores se desplazan detrás del balón. Los del cuadrado sin balón se quedan abiertos esperando.",
            "keys": [
                "Quedarse en la zona libre en vez de ir hacia el balón.",
                "Cambiar el balón de zona en cuanto la presión se acerca.",
                "Mirar antes de recibir dónde está el espacio.",
            ],
            "variant": "Que el cambio de cuadrado tenga que ser de un solo pase.",
        },
        {
            "name": "Juego de posición por zonas fijas",
            "objective": "Ocupar toda la cancha, cada uno en su zona.",
            "organization": "Cancha de 60 × 45 m dividida en 9 zonas (3 × 3). 7 contra 7 con porteros. 3 series de 7 minutos.",
            "development": "Cada jugador de campo tiene una zona asignada y solo uno por equipo puede moverse libre. Así el equipo ocupa todo el ancho y el largo y aprende dónde se crean los espacios.",
            "keys": [
                "Ocupar la zona propia aunque el balón esté lejos.",
                "El jugador libre aparece donde hace falta un apoyo.",
                "Pasar a la zona libre antes de que llegue el rival.",
            ],
            "variant": "Dos jugadores libres por equipo.",
        },
    ],
    "INSUFFICIENT_WIDTH": [
        {
            "name": "Partido con bandas libres",
            "objective": "Abrir la cancha cuando el equipo tiene el balón.",
            "organization": "Cancha de 60 × 45 m con dos pasillos laterales de 8 m. 6 contra 6 dentro y un jugador por equipo en cada pasillo, donde nadie lo puede presionar. 4 series de 6 minutos.",
            "development": "Los jugadores de banda juegan pegados a la línea. El gol que llega después de un pase desde una banda vale doble.",
            "keys": [
                "Los extremos abiertos, con los pies cerca de la línea.",
                "Mover el balón de un lado a otro para abrir espacios por dentro.",
                "El lateral sube cuando el extremo se mete por dentro.",
            ],
            "variant": "Permitir que un defensor entre al pasillo para presionar al de banda.",
        },
        {
            "name": "Rondo ancho 6 contra 3",
            "objective": "Usar todo el ancho del espacio para que la presión no alcance.",
            "organization": "Rectángulo de 40 × 20 m. 6 jugadores con balón contra 3 defensores. Series de 3 minutos.",
            "development": "Los 6 se reparten por el borde del rectángulo y mantienen el balón. Cada pase de un lado ancho al otro suma un punto. Si los defensores recuperan, cambian con los que perdieron.",
            "keys": [
                "Abrirse hasta la línea para estirar a la defensa.",
                "Mover el balón rápido de un lado al otro.",
                "Pasar al lado contrario cuando la presión carga un lado.",
            ],
            "variant": "Agregar un cuarto defensor.",
        },
        {
            "name": "Paredes y centros por la banda",
            "objective": "Llevar el ataque por fuera y terminar con centro.",
            "organization": "Media cancha con portero. Por cada banda, un lateral y un extremo contra un defensor; 2 delanteros contra 2 centrales en el área. Series de 8 ataques.",
            "development": "El lateral y el extremo hacen un 2 contra 1 por la banda (pared o pase por fuera) y terminan con un centro. Los delanteros atacan el primer y el segundo palo.",
            "keys": [
                "El extremo abierto fija al defensor.",
                "El lateral pasa por fuera cuando el extremo conduce hacia dentro.",
                "Los delanteros llegan en el momento del centro, no antes.",
            ],
            "variant": "Agregar un segundo defensor en la banda.",
        },
    ],
    "NUMERICAL_IMBALANCE": [
        {
            "name": "Partido por sectores con jugador libre",
            "objective": "Igualar o superar en número al rival en la zona del balón.",
            "organization": "Cancha de 60 × 45 m dividida en 3 pasillos a lo largo. 2 contra 2 fijos en cada pasillo y un jugador libre por equipo que puede cambiar de pasillo. 4 series de 6 minutos.",
            "development": "El jugador libre se mueve al pasillo del balón para formar un 3 contra 2 cuando su equipo ataca, o para igualar a 3 contra 3 cuando defiende.",
            "keys": [
                "Leer dónde está el balón antes de moverse.",
                "Llegar a tiempo, no antes: si llega pronto, el rival se reorganiza.",
                "Al defender, el más cercano cierra el pasillo del balón.",
            ],
            "variant": "Dos jugadores libres por equipo.",
        },
        {
            "name": "Oleadas 3 contra 2 y 2 contra 1",
            "objective": "Aprovechar la superioridad y defender en inferioridad.",
            "organization": "Cancha de 40 × 30 m con dos porterías y porteros. Grupos de 3 atacantes contra 2 defensores. Series de 10 oleadas.",
            "development": "Tres atacantes atacan contra dos defensores. Cuando termina la jugada, los dos defensores atacan hacia el otro lado contra uno de los atacantes, que defiende solo.",
            "keys": [
                "Atacar rápido el 3 contra 2 antes de que llegue la ayuda.",
                "El defensor en inferioridad temporiza y orienta hacia fuera.",
                "Fijar a un defensor antes de pasar.",
            ],
            "variant": "Que un defensor más entre a los 3 segundos.",
        },
        {
            "name": "Ayuda defensiva en 3 segundos",
            "objective": "Llegar a tiempo a igualar en número cerca del balón.",
            "organization": "Cancha de 30 × 25 m con portería y portero. 2 defensores contra 3 atacantes y un tercer defensor que espera 10 m atrás. Series de 8 ataques.",
            "development": "Los 3 atacantes empiezan con ventaja. A los 3 segundos entra el tercer defensor para igualar a 3 contra 3. Los dos primeros tienen que temporizar hasta que llegue la ayuda.",
            "keys": [
                "Retroceder sin lanzarse mientras llega la ayuda.",
                "Cerrar el centro y dejar al rival por fuera.",
                "El que llega elige al atacante libre más peligroso.",
            ],
            "variant": "La ayuda entra a los 5 segundos.",
        },
    ],
    "DISCONNECTED_TEAM": [
        {
            "name": "Salida por tres zonas",
            "objective": "Mantener conectadas defensa, mediocampo y ataque para que el balón pase de una línea a otra.",
            "organization": "Dos tercios de cancha divididos en 3 zonas: salida, medio y ataque. 9 contra 6. Series de 8 minutos.",
            "development": "El equipo de 9 sale jugando desde el portero y debe pasar el balón por las tres zonas sin saltarse la del medio. Si una línea queda sin un compañero al que pasar en la zona siguiente, la jugada se reinicia.",
            "keys": [
                "Siempre debe haber alguien para recibir en la zona siguiente.",
                "Los mediocampistas se ofrecen entre las líneas rivales.",
                "Cuando el balón avanza, la línea de atrás acompaña.",
            ],
            "variant": "Igualar a 9 contra 8 para aumentar la presión.",
        },
        {
            "name": "Salida con apoyo del pivote",
            "objective": "Unir la defensa con el mediocampo usando al pivote y los interiores.",
            "organization": "Media cancha. 4 defensores, pivote y 2 interiores contra 4 presionadores. Dos porterías pequeñas en la línea media. Series de 5 minutos.",
            "development": "El equipo sale jugando y solo puede marcar en las porterías pequeñas si el balón pasó antes por el pivote o un interior. Los presionadores que recuperan atacan la portería grande.",
            "keys": [
                "El pivote se ofrece entre los presionadores.",
                "Los interiores dan una línea de pase por fuera de la presión.",
                "Los defensores pasan a quien está de cara al juego.",
            ],
            "variant": "Un presionador más.",
        },
        {
            "name": "Gol con el equipo junto",
            "objective": "Que el equipo ataque y defienda como un bloque, sin dejar a nadie descolgado.",
            "organization": "Cancha de 70 × 50 m con porteros y una línea media marcada. 8 contra 8. 3 series de 8 minutos.",
            "development": "El gol solo vale si, en el momento del remate, todos los jugadores de campo del equipo que ataca están en la mitad rival. Si el rival marca mientras algún defensor no llegó a su mitad, el gol vale doble.",
            "keys": [
                "Toda la defensa acompaña el ataque.",
                "Al perder el balón, todos vuelven juntos.",
                "El último defensor da la voz para subir.",
            ],
            "variant": "Que también valga en la línea de tres cuartos.",
        },
    ],
    "ISOLATED_PLAYERS": [
        {
            "name": "Triángulos en movimiento",
            "objective": "Que cada jugador tenga siempre un compañero cerca para pasar o recibir.",
            "organization": "Cancha de 40 × 30 m. Grupos de 3 jugadores con un balón contra 2 defensores. Series de 3 minutos.",
            "development": "Cada grupo avanza de una línea a la otra pasándose el balón sin dejar de formar un triángulo. Los defensores intentan cortar los pases. Un jugador solo, sin compañero a pocos metros, es un pase perdido.",
            "keys": [
                "Moverse después de pasar para dar otra línea de pase.",
                "Ofrecerse en diagonal, no en línea recta.",
                "Ajustar la distancia según la presión.",
            ],
            "variant": "Grupos de 4 contra 3 defensores.",
        },
        {
            "name": "Posesión con apoyo cercano",
            "objective": "No dejar solo al compañero que tiene el balón.",
            "organization": "Cuadrado de 30 × 30 m. 5 contra 5 y 2 comodines. Series de 3 minutos.",
            "development": "Juego de posesión. Quien recibe tiene que tener a un compañero a pocos pasos para un pase de apoyo; si se queda solo y pierde el balón, el rival suma un punto extra.",
            "keys": [
                "Acercarse al poseedor cuando lo presionan.",
                "Ofrecer el apoyo en ángulo, no detrás del rival.",
                "Alejarse de nuevo cuando el balón sale de la presión.",
            ],
            "variant": "Bajar a 25 × 25 m.",
        },
        {
            "name": "Paredes y tercer hombre",
            "objective": "Que siempre haya un segundo y un tercer jugador cerca para combinar.",
            "organization": "Rectángulo de 30 × 20 m con conos como defensores y luego un defensor pasivo. Grupos de 3. 10 minutos.",
            "development": "El grupo avanza combinando: pared entre dos jugadores y pase al tercero que llega. Primero contra conos y después contra un defensor que no entra a robar.",
            "keys": [
                "El tercer hombre se mueve antes de que llegue el pase.",
                "La pared se devuelve a un toque.",
                "Distancias cortas, de 8 a 10 m.",
            ],
            "variant": "Defensor que sí puede robar.",
        },
    ],
    "LOW_BALL_PRESSURE": [
        {
            "name": "Presión tras pérdida de 5 segundos",
            "objective": "Presionar al poseedor justo después de perder el balón.",
            "organization": "Cancha de 40 × 30 m. 6 contra 6 con 2 comodines que juegan con quien tiene el balón. 4 series de 4 minutos.",
            "development": "Juego de posesión. Cuando un equipo pierde el balón tiene 5 segundos para recuperarlo: si lo logra, suma un punto. El rival suma un punto cada 6 pases seguidos.",
            "keys": [
                "El más cercano sale de inmediato al poseedor.",
                "Orientar la presión hacia la banda.",
                "Los demás cierran los pases cortos.",
            ],
            "variant": "Bajar a 3 segundos para recuperar.",
        },
        {
            "name": "Presión 1 contra 1 hacia la banda",
            "objective": "Que el defensor salga rápido al poseedor y lo lleve hacia fuera.",
            "organization": "Pasillo de 15 × 10 m con dos porterías pequeñas: una por dentro y otra pegada a la banda. Duelos 1 contra 1. Series de 6 duelos.",
            "development": "El atacante recibe y quiere marcar en la portería de dentro. El defensor sale mientras el balón viaja y lo orienta hacia la portería de la banda, que vale menos.",
            "keys": [
                "Salir mientras el balón viaja, no cuando ya llegó.",
                "Frenar a un metro y perfilarse para cerrar el lado de dentro.",
                "No lanzarse: obligarlo a ir hacia la banda.",
            ],
            "variant": "Agregar un segundo atacante para el 1 contra 2.",
        },
        {
            "name": "Presión coordinada en trío",
            "objective": "Presionar juntos para encerrar al rival en una zona.",
            "organization": "Cuadrado de 20 × 20 m con una esquina marcada. 3 defensores contra 5 atacantes. Series de 2 minutos.",
            "development": "Los 5 atacantes mantienen el balón. Los 3 defensores presionan juntos para llevar el balón a la esquina marcada: si lo recuperan ahí, valen dos puntos.",
            "keys": [
                "Uno presiona al poseedor y los otros cierran los pases más cercanos.",
                "Presionar con el cuerpo orientado hacia la esquina.",
                "Moverse a la vez que el balón.",
            ],
            "variant": "4 defensores contra 6 atacantes.",
        },
    ],
    "NARROW_ATTACK": [
        {
            "name": "Cambio de orientación",
            "objective": "Atacar usando todo el ancho y cambiar el balón de lado.",
            "organization": "Medio campo con dos porterías. 6 atacantes contra 4 defensores y portero. Conos que marcan dos carriles laterales. Series de 6 ataques.",
            "development": "El gol solo vale si antes el balón pasó por los dos carriles laterales, de uno al otro, en menos de 4 pases.",
            "keys": [
                "Abrir el juego antes de que el rival bascule.",
                "Pase largo al lado débil o circulación rápida por dentro.",
                "El jugador del lado contrario abierto y esperando.",
            ],
            "variant": "Que el gol después de un cambio de orientación de un solo pase valga doble.",
        },
        {
            "name": "Centros y llegada al área",
            "objective": "Terminar las jugadas por fuera, con llegada al área.",
            "organization": "Media cancha con portero. Dos extremos que centran y 3 rematadores que llegan al área. Rotación continua durante 10 minutos.",
            "development": "El extremo conduce por la banda y centra. Los 3 rematadores atacan el primer palo, el segundo palo y el punto de penal. Después se agregan 2 defensores.",
            "keys": [
                "Cada rematador ataca una zona distinta.",
                "Llegar en carrera, no esperar quieto.",
                "El extremo levanta la cabeza antes de centrar.",
            ],
            "variant": "Con 2 defensores y un portero activo.",
        },
        {
            "name": "Partido de cuatro porterías en las esquinas",
            "objective": "Invitar al equipo a atacar por fuera.",
            "organization": "Cancha de 50 × 40 m con 4 porterías pequeñas, una en cada esquina. 6 contra 6. 3 series de 6 minutos.",
            "development": "Cada equipo ataca las dos porterías de una línea de fondo y defiende las otras dos. Como las porterías están en las esquinas, el equipo tiene que abrir el juego y cambiar de lado para marcar.",
            "keys": [
                "Atacar la portería del lado contrario al que defiende el rival.",
                "Abrir el juego antes de llegar a la zona de remate.",
                "Cambiar de lado con pocos pases.",
            ],
            "variant": "Que el gol después de un cambio de lado valga doble.",
        },
    ],
    "NO_ATTACKING_DEPTH": [
        {
            "name": "Desmarque de ruptura",
            "objective": "Tener jugadores por delante del balón que ataquen la espalda de la defensa.",
            "organization": "Último tercio de cancha. 4 atacantes contra 3 defensores y portero. Series de 6 ataques.",
            "development": "El ataque debe tener siempre al menos un jugador por delante de la línea del balón. El gol que llega después de un pase a la espalda de la defensa vale doble.",
            "keys": [
                "Romper en el momento en que el poseedor levanta la cabeza.",
                "Arrancar en diagonal para no quedar en fuera de lugar.",
                "Un jugador fija a la defensa y otro rompe.",
            ],
            "variant": "Agregar un defensor que llega desde atrás para cerrar el espacio.",
        },
        {
            "name": "Pase al espacio 3 contra 2",
            "objective": "Atacar la espalda de la defensa con pases y desmarques al espacio.",
            "organization": "Cancha de 30 × 25 m con portería y portero, y una línea a 12 m de la portería. 3 atacantes contra 2 defensores. Series de 8 ataques.",
            "development": "Los atacantes solo pueden rematar después de recibir detrás de la línea de 12 m con un pase al espacio. Los defensores intentan mantener la línea y cortar ese pase.",
            "keys": [
                "Un atacante fija a la defensa y otro rompe por detrás.",
                "El pase va al espacio, delante del que corre.",
                "Romper en diagonal para no quedar en fuera de lugar.",
            ],
            "variant": "Agregar un tercer defensor.",
        },
        {
            "name": "Partido de zona final",
            "objective": "Que el equipo busque siempre jugadores por delante del balón.",
            "organization": "Cancha de 50 × 40 m con una zona final de 8 m en cada fondo. 7 contra 7, sin porteros. 3 series de 7 minutos.",
            "development": "Se marca un punto cuando un jugador recibe un pase dentro de la zona final del rival, como en el rugby. Sin desmarques hacia adelante no hay forma de sumar.",
            "keys": [
                "Siempre debe haber alguien amenazando la zona final.",
                "Desmarcarse en el momento del pase, no antes.",
                "Si el pase adelante no está, mover el balón y volver a intentar.",
            ],
            "variant": "Que solo valga el pase a un jugador que entra corriendo a la zona.",
        },
    ],
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


def drills_for(title: str) -> list[dict]:
    """The suggested exercises of a stored possible issue (by its title), the main one first; empty when
    the title is not one of the AI rules."""
    code = TITLE_TO_CODE.get(title.strip())
    if code is None:
        return []
    return [{"code": code, **drill, "note": NOTE} for drill in DRILLS[code]]
