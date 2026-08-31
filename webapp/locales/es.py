"""The Spanish translation of :mod:`webapp.locales.en`."""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    # ---------------------------------------------------------------- site
    "site.og_image_alt": (
        "OpenCloud Security Scan: comprueba una instancia en busca de "
        "vulnerabilidades conocidas, medidas de refuerzo faltantes y "
        "cabeceras de seguridad débiles"
    ),
    # ------------------------------------------------------- header chrome
    "chrome.skip_to_content": "Saltar al contenido",
    "chrome.brand": "Análisis de seguridad para OpenCloud",
    "chrome.menu": "Menú",
    "chrome.nav.primary": "Principal",
    "chrome.nav.secondary": "Secundaria",
    "chrome.search.label": "Buscar en la documentación",
    "chrome.search.placeholder": "Buscar",
    "chrome.back_to_top": "Volver arriba",
    "nav.new_scan": "Nuevo análisis",
    "nav.how_it_works": "Cómo funciona",
    "nav.grades": "Calificaciones",
    "nav.catalogue": "Catálogo",
    "nav.docs": "Documentación",
    "nav.search": "Buscar",
    "nav.api": "API",
    "nav.ai": "IA",
    "nav.privacy": "Privacidad",
    "nav.about": "Acerca de",
    # --------------------------------------------------- language switcher
    "lang.region": "Idioma",
    "lang.label": "Idioma de la página",
    "lang.apply": "Cambiar idioma",
    "lang.note": "El análisis en sí no cambia; solo esta página se traduce.",
    # ------------------------------------------------------------- footer
    "footer.note.title": "Un servicio discreto, por diseño.",
    "footer.note.body": (
        "Los análisis se ejecutan desde este servidor contra la dirección que "
        "introduces. Los resultados permanecen en memoria durante {minutes} "
        "minutos y luego desaparecen. Construido sobre el escáner "
        "<code>check-opencloud-security</code>: sin rastreadores, sin cuentas, "
        "sin analítica."
    ),
    "footer.note.run_yourself": "Ejecútalo tú mismo",
    "footer.version.title": "La versión del escáner que produjo estos resultados",
    "footer.version.label": "Backend v{version}",
    "footer.legal.scope": (
        "<strong>Esta comprobación no es exhaustiva, y una buena calificación "
        "no es un certificado.</strong> Analiza lo que una instancia de "
        "OpenCloud accesible públicamente muestra a un visitante anónimo: su "
        "versión, los avisos de seguridad contra esa versión, su transporte, "
        "sus cabeceras y un conjunto de ajustes visibles sin iniciar sesión. "
        "Una &ldquo;A&rdquo; significa que nada de eso falló, no que la "
        "instancia sea segura. Todo lo que hay detrás del inicio de sesión, el "
        "servidor en el que se ejecuta, la red que la rodea, los datos que "
        "contiene y las personas con cuentas en ella quedan fuera de lo que "
        "cualquier análisis no autenticado puede ver. Trata el resultado como "
        "una entrada más entre varias, nunca como una auditoría de seguridad o "
        "una prueba de penetración."
    ),
    "footer.legal.trademark": (
        "Este es un proyecto comunitario independiente. No está afiliado a "
        "OpenCloud GmbH y la empresa ni lo recomienda ni lo respalda. "
        "&ldquo;OpenCloud&rdquo;, el logotipo de OpenCloud y todas las marcas "
        "asociadas son propiedad de sus respectivos titulares y se usan aquí "
        "únicamente para indicar qué software comprueba esta herramienta."
    ),
    # --------------------------------------------------- the contents list
    "toc.heading": "En esta página",
    "toc.aria": "En esta página",
    # --------------------------------------------------------- cross-links
    "pagenav.kicker": "Sigue leyendo",
    "pagenav.aria": "Más sobre este servicio",
    "pagenav.how.title": "Cómo funciona el análisis",
    "pagenav.how.blurb": (
        "Qué se comprueba, y los cuatro pasos entre el botón y la calificación."
    ),
    "pagenav.grades.title": "Qué significan las calificaciones",
    "pagenav.grades.blurb": (
        "Cada nivel de A+ a F, qué frena una calificación y cómo mejorarla."
    ),
    "pagenav.catalogue.title": "Qué comprueba el escáner",
    "pagenav.catalogue.blurb": (
        "Cada indicador de refuerzo, cabecera y comprobación TLS, y cada "
        "vulnerabilidad conocida - independiente de un análisis concreto."
    ),
    "pagenav.docs.title": "Documentación de la CLI",
    "pagenav.docs.blurb": "Instala, configura y automatiza el escáner desde una terminal.",
    "pagenav.api.title": "Analizar desde un script",
    "pagenav.api.blurb": "La API JSON, los límites de uso razonable y el esquema OpenAPI.",
    "pagenav.ai.title": "Para agentes de IA",
    "pagenav.ai.blurb": "Descubrimiento, OpenAPI, flujos de trabajo Arazzo y el endpoint MCP.",
    "pagenav.privacy.title": "Qué conserva este servidor",
    "pagenav.privacy.blurb": (
        "En memoria, durante {minutes} minutos, y qué queda fuera del registro."
    ),
    "pagenav.about.title": "Acerca de OpenCloud",
    "pagenav.about.blurb": (
        "La plataforma que esto comprueba, y por qué este proyecto es "
        "independiente de ella."
    ),
    "pagenav.cta.title": "Analizar una instancia",
    "pagenav.cta.blurb": "Vuelve al formulario. Tarda unos segundos, sin registro.",
    # ---------------------------------------------------------------- 404
    "notfound.title": "Aquí no hay nada",
    "notfound.description": (
        "La dirección no existe, o el análisis al que apuntaba ya ha expirado."
    ),
    "notfound.kicker": "No encontrado",
    "notfound.lede": (
        "O bien la dirección no existe, o era un análisis y ese análisis ya no "
        "está: los resultados se conservan durante {minutes} minutos y luego "
        "se eliminan, así que un enlace de hace unas horas no se abrirá. Un "
        "identificador que nunca existió se ve exactamente igual desde aquí; "
        "este servicio no puede decirte cuál es el caso, y deliberadamente no "
        "lo intenta."
    ),
    "notfound.action": "Ejecutar un nuevo análisis",
    # ------------------------------------------------------- landing page
    "index.title": "Analizar una instancia de OpenCloud",
    "index.description": (
        "Comprueba una instancia de OpenCloud en busca de vulnerabilidades "
        "conocidas, medidas de refuerzo faltantes y cabeceras de seguridad "
        "débiles. Gratuito, independiente y sin almacenar nada."
    ),
    "index.eyebrow": "Independiente &middot; aislado &middot; sin almacenamiento",
    "index.headline": '¿Qué tan segura es tu <em class="swash">instancia de OpenCloud</em>?',
    "index.lede": (
        "Introduce la dirección de una instancia de la que seas responsable. "
        "Este servidor se comunica con ella por HTTPS como lo haría cualquier "
        "visitante, lee lo que publica sin iniciar sesión y califica el "
        "resultado de <strong>A+</strong> a <strong>F</strong>."
    ),
    "index.form.kicker": "Solicitud de análisis",
    "index.form.hint": "Unos segundos &middot; sin registro",
    "index.error.self_host": (
        "Sin rencores: los límites son lo que mantiene en pie a este pequeño "
        "servicio. El escáner es de código abierto, así que puedes ejecutar "
        "esta misma comprobación tú mismo, tantas veces como quieras:"
    ),
    "index.field.label": "Dirección de la instancia",
    "index.field.title": (
        "La dirección base de la instancia: un nombre de host, un puerto "
        "opcional y una subcarpeta simple opcional. Sin consultas, "
        "fragmentos, parámetros, escapes ni recorridos de ruta."
    ),
    "index.field.hint": (
        "Basta con el nombre de host; se asume <code>https://</code>. Se "
        "admite una subcarpeta como <code>/opencloud</code>; se rechazan "
        "consultas, fragmentos, parámetros y recorridos de ruta. Solo "
        "direcciones públicas, y solo instancias que administras o para las "
        "que tienes permiso de comprobación."
    ),
    "index.submit": "Iniciar auditoría",
    "index.submit.busy": "Iniciando auditoría...",
    "index.track.label": "Canal de publicación",
    "index.track.hint": (
        "Determina durante cuánto tiempo se admite esta versión y a cuál se "
        "le indica que debe actualizar."
    ),
    "index.format.label": "Mostrar",
    "index.format.dashboard": "Un panel",
    "index.format.json": "El JSON en bruto",
    "index.format.hint": "Ambos provienen del mismo análisis.",
    "index.waivers.summary": "Ignorar comprobaciones específicas (opcional)",
    "index.waivers.selected": "Ignorar comprobaciones específicas ({count} seleccionadas)",
    "index.waivers.hint": (
        "Una comprobación exceptuada permanece en el informe y sigue "
        "mostrándose; simplemente deja de frenar la calificación. Solo se "
        "pueden exceptuar las comprobaciones que realmente fallaron."
    ),
    "index.assurance.aria": "Cómo maneja este servicio tus datos",
    "index.assurance.airgapped.title": "100% aislado",
    "index.assurance.airgapped.body": (
        "Cada byte proviene de este origen. Sin CDN, sin servicio de fuentes, "
        "sin analítica."
    ),
    "index.assurance.nostore.title": "Sin almacenamiento de datos",
    "index.assurance.nostore.body": (
        "El resultado vive en memoria y se elimina en cuanto expira."
    ),
    "index.assurance.noaccount.title": "No se necesita registro",
    "index.assurance.noaccount.body": (
        "Sin cuenta, sin registro, sin dirección de correo, sin esperas."
    ),
    "index.assurance.ephemeral.title": "Resultados efímeros",
    "index.assurance.ephemeral.body": (
        "El enlace deja de funcionar {minutes} minutos después del análisis."
    ),
    # -------------------------------------------- release tracks and waivers
    "track.auto.label": "Detectar automáticamente",
    "track.auto.description": (
        "Deducir el canal a partir de la versión que reporta la instancia."
    ),
    "track.rolling.label": "Rolling",
    "track.rolling.description": "Una nueva versión aproximadamente cada tres semanas.",
    "track.production.label": "Production",
    "track.production.description": (
        "Compatible durante unos seis meses. La opción habitual."
    ),
    "track.lts.label": "LTS",
    "track.lts.description": "Compatible durante dos años.",
    "waivers.group.hardening": "Refuerzo",
    "waivers.group.headers": "Cabeceras",
    "waivers.group.checks": "Comprobaciones",
    # ------------------------------------------------------------ severity
    "severity.critical": "crítica",
    "severity.high": "alta",
    "severity.medium": "media",
    "severity.low": "baja",
    # ------------------------------------------------------------ category
    "category.transport": "Transporte y TLS",
    "category.cookies": "Cookies",
    "category.headers": "Cabeceras de seguridad",
    "category.authentication": "Autenticación y cuentas",
    "category.sharing": "Uso compartido y enlaces",
    "category.exposure": "Exposición de red",
    "category.embedding": "Incrustación",
    "category.lifecycle": "Versión y ciclo de vida",
    "category.proxy": "Proveedor de identidad y proxy",
    # --------------------------------------------------------- grade scale
    "grade.5.headline": "No se ha encontrado nada",
    "grade.5.meaning": (
        "La versión está actualizada para su canal, ningún aviso de seguridad "
        "coincide con ella, y todas las comprobaciones que el análisis pudo "
        "ejecutar se superaron."
    ),
    "grade.5.improve": (
        "Mantente aquí: vigila la siguiente versión de tu canal, y vuelve a "
        "ejecutar el análisis tras cualquier cambio en el proxy inverso o en "
        "el inicio de sesión."
    ),
    "grade.4.headline": "Hay una actualización pendiente",
    "grade.4.meaning": (
        "Existe una versión de parche más reciente en la misma línea de "
        "versiones. No se sabe que la instalada tenga ningún problema; "
        "simplemente no es la más reciente."
    ),
    "grade.4.improve": (
        "Instala la actualización pendiente. Es la misma línea de versiones, "
        "así que es la actualización más pequeña posible."
    ),
    "grade.3.headline": "Una línea de versiones por detrás",
    "grade.3.meaning": (
        "La instancia ejecuta una línea más antigua que la actual para su "
        "canal. Puede que todavía tenga soporte, pero ya no es donde llegan "
        "primero las correcciones."
    ),
    "grade.3.improve": (
        "Sube a la línea actual de tu canal. El análisis indica cuál es, y "
        "nunca señala un canal que no hayas elegido."
    ),
    "grade.2.headline": "Hay avisos de seguridad que coinciden con esta versión",
    "grade.2.meaning": (
        "La versión instalada aparece en la base de datos de avisos de "
        "seguridad. Ninguno de los avisos coincidentes está calificado como "
        "crítico o alto, que es la única razón por la que esto no es más bajo."
    ),
    "grade.2.improve": (
        "Actualiza a la versión corregida para tu línea de versiones. La "
        "página de resultados la indica; un mismo aviso puede corregirse por "
        "separado en varias líneas."
    ),
    "grade.1.headline": "Coincide un aviso crítico o alto",
    "grade.1.meaning": (
        "Al menos un aviso que coincide con la versión instalada está "
        "calificado como crítico o alto. Se trata de una vía de entrada "
        "conocida, publicada y ya corregida."
    ),
    "grade.1.improve": (
        "Actualiza ahora, antes que cualquier otra cosa en la página. Ningún "
        "otro cambio posible elevará la calificación por encima de esta."
    ),
    "grade.0.headline": "Sin soporte",
    "grade.0.meaning": (
        "La línea de versiones no recibe ninguna corrección de seguridad. "
        "Esto anula cualquier otra señal, incluida una exención: una "
        "instancia que nadie parchea no puede calificarse por lo ordenadas "
        "que sean sus cabeceras."
    ),
    "grade.0.improve": (
        "Pasa a una línea de versiones compatible. Qué líneas tienen soporte, "
        "y durante cuánto tiempo, figura en el calendario de versiones que "
        "consulta el análisis."
    ),
    # ---------------------------------------------------------- grades page
    "grades.title": "Qué significan las calificaciones",
    "grades.description": (
        "A+, A, C, D, E y F: qué dice cada calificación sobre una instancia de "
        "OpenCloud, qué la frena, y el camino más corto hasta la siguiente."
    ),
    "grades.kicker": "La escala",
    "grades.lede": (
        "Cada análisis termina en una letra. Se calcula a partir de dos "
        "factores: qué versión ejecuta la instancia y qué comprobaciones "
        "fallaron. Esta página recoge toda esa aritmética, en el mismo orden "
        "en que la aplica el escáner."
    ),
    "grades.scale.kicker": "Seis niveles",
    "grades.scale.heading": "La escala, de mejor a peor",
    "grades.scale.intro": (
        "La escala <strong>0-5</strong> y sus letras son las que "
        "<code>scan.nextcloud.com</code> hizo familiares, conservadas "
        "deliberadamente para que un umbral, un gráfico o una regla de alerta "
        "existentes sigan teniendo el mismo significado. Por eso tampoco "
        "existe la <strong>B</strong>: la escala la omite, e inventar una aquí "
        "haría que dos números significasen la misma calificación."
    ),
    "grades.row.prefix": "Calificación {label}: ",
    "grades.row.score": "{rating} de 5",
    "grades.row.improve": "Para mejorar:",
    "grades.caps.kicker": "El techo",
    "grades.caps.heading": "Qué puede hacerle a una calificación una comprobación fallida",
    "grades.caps.intro": (
        "La versión establece la calificación de partida. Las comprobaciones "
        "fallidas no pueden elevarla; solo pueden frenarla, y hasta qué punto "
        "depende de la gravedad de la peor que haya fallado:"
    ),
    "grades.caps.at_best": "como máximo",
    "grades.caps.shared": (
        "Los hallazgos de la misma gravedad comparten un único techo, así que "
        "corregir uno de tres hallazgos medios no cambia nada hasta que "
        "desaparece el último. Por eso la página de resultados ordena el plan "
        "como lo hace, y por eso indica la calificación que realmente "
        "alcanzaría cada paso."
    ),
    "grades.caps.rules": (
        "Por encima de todo esto hay dos reglas. <strong>El fin de vida útil "
        "anula todo lo demás</strong>, incluida una exención: una línea de "
        "versiones que no recibe correcciones de seguridad es una "
        "<strong>F</strong>, por limpio que esté el resto del informe. Y "
        "<strong>ir por delante de tu canal no es ir por detrás de él</strong> "
        "- una versión más reciente que la actual del canal declarado se "
        "reporta como adelantada y nunca se califica como no compatible."
    ),
    "grades.improve.kicker": "El camino más corto",
    "grades.improve.heading": "Cómo te ayuda este escáner a mejorar",
    "grades.improve.intro": (
        "Una calificación por sí sola es un marcador, que de poco sirve a "
        "media tarde. Cada página de resultados incluye también los cuatro "
        "elementos que la convierten en el trabajo de una tarde:"
    ),
    "grades.improve.plan": (
        "<strong>Un plan de corrección, ordenado por rentabilidad.</strong> "
        "Cada paso indica qué cambiar y qué calificación mantendría la "
        "instancia una vez completado ese paso y todos los anteriores, para "
        "que puedas detenerte donde lo hace el beneficio."
    ),
    "grades.improve.release": (
        '<strong>La versión exacta a la que pasar.</strong> No "actualiza": '
        "la versión que corrige el aviso <em>en la línea en la que realmente "
        'estás</em>, y nunca un salto a un canal que no elegiste.'
    ),
    "grades.improve.explained": (
        "<strong>Cada comprobación fallida, explicada.</strong> Qué se midió, "
        "por qué importa y cómo corregirlo, con un enlace a la documentación "
        "de OpenCloud para el ajuste correspondiente."
    ),
    "grades.improve.waiver": (
        "<strong>Una exención para lo que has decidido asumir.</strong> Una "
        "comprobación exceptuada permanece en el informe y sigue siendo "
        "visible; simplemente deja de limitar la calificación, de modo que "
        "una decisión meditada no se lea como un fallo para siempre. No puede "
        "ocultar una comprobación que ya se supera, ni puede rescatar una "
        "versión fuera de soporte."
    ),
    "grades.improve.rerun": (
        "Vuelve a ejecutarlo después. La misma instancia, el mismo análisis, "
        "y la letra cambia; esa es la única prueba de que algo funcionó."
    ),
    "grades.limits.kicker": "Honestidad",
    "grades.limits.heading": "Lo que una buena calificación no es",
    "grades.limits.body": (
        "Una <strong>A+</strong> significa que nada de lo que examinó este "
        "análisis falló. No es un certificado, y no es una prueba de "
        "penetración. Todo lo que hay detrás del inicio de sesión, el sistema "
        "operativo, el entorno de ejecución de contenedores, las copias de "
        "seguridad, las cuentas y las personas que las poseen quedan fuera de "
        "lo que un análisis no autenticado puede ver. Trata la letra como una "
        'entrada más entre varias: <a href="/how-it-works">cómo funciona el '
        "análisis</a> enumera lo que lee, y cada página de resultados repite "
        "los límites justo debajo de la calificación."
    ),
    # -------------------------------------------------------------- catalogue
    "catalogue.title": "Qué comprueba el escáner",
    "catalogue.description": (
        "Cada indicador de refuerzo, cabecera de seguridad, comprobación TLS y "
        "vulnerabilidad conocida que este escáner puede reportar, "
        "independiente de un resultado de análisis concreto."
    ),
    "catalogue.kicker": "Referencia",
    "catalogue.lede": (
        "Este es el conjunto completo: cada comprobación de abajo puede "
        "aparecer en una página de resultados, y cada vulnerabilidad de abajo "
        "es una contra la que se evalúa un análisis. Nada aquí depende de una "
        "instancia concreta."
    ),
    "catalogue.checks.kicker": "Comprobaciones",
    "catalogue.checks.heading": "Cada comprobación, por categoría",
    "catalogue.checks.lede": (
        "Agrupadas por tema en lugar de por gravedad - la gravedad depende de "
        "la instancia analizada, así que no se muestra aquí."
    ),
    "catalogue.checks.not_configurable": "no configurable",
    "catalogue.advisories.kicker": "Vulnerabilidades",
    "catalogue.advisories.heading": "Vulnerabilidades conocidas",
    "catalogue.advisories.lede": (
        "Cada vulnerabilidad de la base de datos contra la que se evalúa un "
        "análisis, actualizada a diario desde el feed público."
    ),
    "catalogue.advisories.empty.tag": "Ninguna conocida",
    "catalogue.advisories.empty.body": (
        "La base de datos de vulnerabilidades está actualmente vacía."
    ),
    "catalogue.advisories.fixed_in": "Corregido en {version}",
    "catalogue.advisories.unfixed": "Aún no hay corrección publicada",
    # -------------------------------------------------- how the scan works
    "how.title": "Cómo funciona el análisis",
    "how.description": (
        "Qué comprueba este escáner en una instancia de OpenCloud, y qué "
        "ocurre entre pulsar el botón y leer la calificación."
    ),
    "how.kicker": "El método",
    "how.lede": (
        "Todo lo que reporta este servicio lo determina por sí mismo, "
        "comunicándose con la dirección que introduces por HTTPS como lo "
        "haría cualquier visitante. No se pide nada a terceros, y no se "
        "inicia sesión en ningún sitio."
    ),
    "how.tests.heading": "Qué se comprueba",
    "how.tests.version.title": "Versión y ciclo de vida",
    "how.tests.version.body": (
        "Qué versión se ejecuta, si todavía recibe correcciones de seguridad, "
        "y si algún aviso publicado coincide con ella. Una versión que ya "
        "alcanzó su fin de vida útil es una F, por muy bien que esté todo lo "
        "demás."
    ),
    "how.tests.transport.title": "Transporte y cabeceras",
    "how.tests.transport.body": (
        "La accesibilidad por HTTPS, el certificado y su vida útil restante, "
        "las versiones de TLS ofrecidas, y las cabeceras de seguridad que "
        "realmente se envían a un navegador: HSTS, CSP, protección contra "
        "framing y de tipo de contenido."
    ),
    "how.tests.hardening.title": "Refuerzo y exposición",
    "how.tests.hardening.body": (
        "Autenticación básica, política de contraseña y caducidad de enlaces "
        "públicos, reglas de contraseñas, listado de directorios, endpoints "
        "expuestos y cualquier cosa que anuncie la versión al mundo."
    ),
    "how.pipeline.kicker": "El proceso",
    "how.pipeline.heading": "Qué ocurre cuando pulsas el botón",
    "how.pipeline.lede": "Cuatro pasos, y en el tercero es donde entra en juego la cola.",
    "how.pipeline.step1": (
        "<strong>Se comprueba tu dirección.</strong> Las direcciones "
        "privadas, de loopback y de metadatos de la nube se rechazan antes de "
        "que se establezca ninguna conexión."
    ),
    "how.pipeline.step2": (
        "<strong>Un análisis recibe un identificador aleatorio.</strong> Ese "
        "identificador es la única forma de acceder al resultado. No existe "
        "ninguna lista de análisis, ni forma de adivinar uno."
    ),
    "how.pipeline.step3": (
        "<strong>Espera su turno.</strong> Un número fijo de análisis se "
        "ejecutan a la vez. Si todos están ocupados, el tuyo se pone en cola "
        "y se te indica en qué posición estás - nada se rechaza porque el "
        "servicio tenga mucha demanda."
    ),
    "how.pipeline.step4": (
        "<strong>El resultado expira.</strong> Tras {minutes} minutos el "
        "identificador deja de funcionar y el resultado desaparece, sin que "
        "nada se haya escrito en disco."
    ),
    "how.faq.kicker": "Preguntas",
    "how.faq.heading": "Preguntas frecuentes",
    "how.faq.q1": "¿Es este el software oficial de OpenCloud?",
    "how.faq.a1": (
        "No. Este es un proyecto comunitario independiente, no afiliado a "
        "OpenCloud GmbH y que la empresa ni recomienda ni respalda. "
        '"OpenCloud" y su logotipo son marcas de sus respectivos titulares, '
        "usadas aquí únicamente para indicar qué software comprueba esta "
        "herramienta."
    ),
    "how.faq.q2": "¿Una buena calificación significa que una instancia es segura?",
    "how.faq.a2": (
        "No. El análisis solo lee lo que una instancia accesible públicamente "
        "muestra a un visitante anónimo: su versión, los avisos de seguridad "
        "contra esa versión, su transporte, sus cabeceras y un conjunto de "
        "ajustes visibles sin iniciar sesión. Todo lo que hay detrás del inicio "
        "de sesión, el servidor en el que se ejecuta, la red que la rodea y las "
        "personas con cuentas en ella quedan fuera de lo que puede ver un "
        "análisis sin autenticar. Trata un resultado como una señal más entre "
        "varias, nunca como una auditoría de seguridad ni una prueba de "
        "penetración."
    ),
    "how.faq.q3": "¿Cuánto tiempo conserváis el resultado de un análisis?",
    "how.faq.a3": (
        "Solo en memoria, durante {minutes} minutos, y luego desaparece. Sin "
        "cuentas, sin analítica, sin rastreadores - el resto está en "
        '<a href="/privacy">qué conserva este servidor</a>.'
    ),
    "how.faq.q4": "¿Hay un límite de frecuencia?",
    "how.faq.a4": (
        "Sí, por visitante y por objetivo analizado, para que ni un visitante "
        "ocupado acapare la cola ni la misma instancia se analice una y otra "
        "vez seguidas. Las cifras exactas de este despliegue están en la "
        '<a href="/api#api-limits">página de la API</a>.'
    ),
    "how.faq.q5": "¿Puedo analizar sin límite de frecuencia?",
    "how.faq.a5": (
        "Sí: el escáner es de código abierto. Ejecútalo tú mismo con "
        '<a href="/cli">un único comando de Docker</a> en tu propia máquina, '
        "sin límite y sin ningún sitio web de por medio."
    ),
    "how.faq.q6": "¿Un escaneo me indica si hay una actualización de OpenCloud pendiente?",
    "how.faq.a6": (
        "Sí. Cada escaneo compara la versión indicada con el feed de versiones "
        "de OpenCloud e informa de una actualización pendiente o una versión "
        "sin soporte igual que informaría de un encabezado faltante - consulta "
        '<a href="/documentation/reference#update-check">la verificación de '
        "actualizaciones</a> para saber cómo se determina la versión "
        "recomendada."
    ),
    # --------------------------------------------------------------- privacy
    "privacy.title": "Qué conserva este servidor",
    "privacy.description": (
        "Qué se almacena mientras se ejecuta un análisis, durante cuánto "
        "tiempo, y qué registra y qué no registra el registro operativo."
    ),
    "privacy.kicker": "Privacidad",
    "privacy.lede": "Respuesta breve: el análisis, durante {minutes} minutos, en memoria.",
    "privacy.retention.kicker": "Retención",
    "privacy.retention.heading": "Mientras un análisis está activo",
    "privacy.retention.body": (
        "La dirección que envías, las comprobaciones que decidiste exceptuar "
        "y el resultado permanecen en memoria durante {minutes} minutos, bajo "
        "una clave derivada del identificador aleatorio de tu análisis, y "
        "luego el propio almacén los elimina. El registro operativo anota que "
        "un análisis se creó, se inició y finalizó, identificado únicamente "
        "por ese identificador aleatorio, nunca por la dirección, el "
        "resultado ni tu dirección IP, que solo se cuenta como una huella "
        "unidireccional para la limitación de frecuencia."
    ),
    "privacy.self_host": (
        "¿Prefieres ejecutarlo tú mismo? El mismo escáner es una comprobación "
        "de línea de comandos y un paquete de Python. En ningún caso se "
        "comunica nada de esto con un servicio de terceros."
    ),
    # ----------------------------------------------------------- legal notice
    "legal.title": "Aviso legal",
    "legal.description": (
        "Identificación del prestador, datos de contacto y advertencias de "
        "responsabilidad del operador de esta instalación."
    ),
    "legal.kicker": "Aviso legal",
    "legal.lede": (
        "Identificación del prestador conforme al derecho alemán, para el "
        "operador de esta instalación."
    ),
    "legal.english_notice": (
        "Este aviso es el texto legal del propio operador y solo está "
        "disponible en inglés. La página que lo rodea está traducida; el texto "
        "de abajo no."
    ),
    # ----------------------------------------------------------------- about
    "about.title": "Acerca de OpenCloud y de este escáner",
    "about.description": (
        "Qué es OpenCloud, quién lo desarrolla, y por qué este escáner es un "
        "proyecto comunitario independiente."
    ),
    "about.kicker": "Acerca de",
    "about.lede": (
        "Uno es una plataforma de archivos, sincronización y compartición. El "
        "otro es una comprobación comunitaria que la observa desde fuera."
    ),
    "about.platform.kicker": "La plataforma",
    "about.platform.heading": "Acerca de OpenCloud",
    "about.platform.body": (
        '<a href="https://opencloud.eu/" rel="noopener noreferrer">OpenCloud</a> '
        "es la plataforma de archivos, sincronización y compartición que "
        "comprueba esta herramienta: de código abierto, desarrollada en "
        "Alemania, y documentada en "
        '<a href="https://docs.opencloud.eu/" rel="noopener noreferrer">'
        "docs.opencloud.eu</a>, donde se explica correctamente cada "
        "corrección que sugiere este escáner. Gracias a las personas que la "
        "desarrollan."
    ),
    "about.platform.independent": (
        "Este escáner es un proyecto comunitario independiente. No está "
        "afiliado a OpenCloud GmbH y la empresa ni lo recomienda ni lo "
        "respalda. &ldquo;OpenCloud&rdquo;, el logotipo de OpenCloud y todas "
        "las marcas asociadas son propiedad de sus respectivos titulares."
    ),
    "about.project.kicker": "El proyecto",
    "about.project.heading": "Acerca de este escáner",
    "about.project.body": (
        "Todo lo que ves aquí lo produce "
        "<code>check-opencloud-security</code>, un complemento para Nagios e "
        "Icinga respaldado por una biblioteca de escaneo. Esta página es una "
        "forma de usarlo; un comando en tu propia máquina, sin límite de "
        "frecuencia y sin cola, es la otra."
    ),
    "about.project.origin": (
        "El proyecto fue creado por <strong>Massoud Ahmed</strong> para dar a "
        "los usuarios de OpenCloud una alternativa independiente a "
        "<code>scan.nextcloud.com</code>: un escáner construido para los "
        "canales de publicación, los ajustes y el modelo de despliegue de "
        "OpenCloud, que puede ejecutarse íntegramente en la propia máquina "
        'del operador. <a href="{project}" rel="noopener noreferrer">'
        "El proyecto está en GitHub</a>."
    ),
    # ------------------------------------------------------------------- API
    "api.title": "Analizar desde un script",
    "api.description": (
        "La API JSON detrás del formulario: cómo enviar un análisis, "
        "consultarlo, y qué se niega este servidor a dejar decidir a quien "
        "lo llama."
    ),
    "api.kicker": "La API",
    "api.lede": (
        "El formulario es una de las dos puertas de entrada; la otra es "
        "JSON, y es el mismo controlador."
    ),
    "api.submit.kicker": "Enviar y consultar",
    "api.submit.heading": "Enviar y consultar",
    "api.submit.body": (
        "Un envío responde <code>202</code> con el identificador del "
        "análisis; al consultarlo se obtiene <code>queued</code>, "
        "<code>running</code> o el resultado terminado, y <code>404</code> "
        "una vez ha expirado. Solo se leen cuatro campos: la dirección, las "
        "comprobaciones a exceptuar, el canal de publicación y el formato de "
        "salida. Cualquier otra cosa en el cuerpo, sobre todo la concurrencia "
        "y los tiempos de espera, se rechaza: la intensidad con la que este "
        "servidor analiza no es decisión de quien lo llama."
    ),
    "api.limits.kicker": "Uso razonable",
    "api.limits.heading": "Uso razonable",
    "api.limits.enforced": (
        "El uso razonable se impone, no se solicita: {client} envíos por "
        "{window} minuto(s) desde una misma dirección, y {cooldown}, ambos "
        "respondidos con <code>429</code> y un <code>Retry-After</code>."
    ),
    "api.limits.cooldown": "un análisis por objetivo cada {minutes} minuto(s)",
    "api.limits.no_cooldown": "sin tiempo de espera por objetivo",
    "api.limits.none": "Este despliegue no establece ningún límite de frecuencia.",
    "api.limits.self_host": (
        "Si te encuentras con uno y prefieres no esperar, todo esto se "
        'ejecuta también en tu propia máquina: <a href="{project}" '
        'rel="noopener noreferrer">el proyecto está en GitHub</a>.'
    ),
    "api.schema.kicker": "El esquema",
    "api.schema.heading": "El esquema",
    "api.schema.body": (
        "Los documentos legibles por máquina son siempre públicos, en este "
        'despliegue y en cualquier otro: la <a href="/openapi.json">'
        "descripción OpenAPI 3.1</a> de cada operación, y los "
        '<a href="/arazzo.json">flujos de trabajo Arazzo 1.0.1</a> que '
        "indican cómo se combinan esas operaciones para enviar un análisis, "
        "esperarlo y recoger el resultado."
    ),
    "api.schema.docs_on": (
        'Ambos se pueden explorar aquí como <a href="/docs">Swagger UI</a> y '
        '<a href="/redoc">ReDoc</a>, servidos desde este servidor como todo '
        "lo demás; nada se obtiene de ningún otro sitio."
    ),
    "api.schema.docs_off": (
        "Los visores interactivos (Swagger UI en <code>/docs</code>, ReDoc "
        "en <code>/redoc</code>) están desactivados en este despliegue; un "
        "operador los activa con <code>COS_WEB_ENABLE_DOCS=true</code>."
    ),
    "api.agents.kicker": "Agentes",
    "api.agents.heading": "Para agentes de IA",
    "api.agents.body": (
        "El software que no se escribió pensando en este servicio tiene su "
        'propia página: <a href="/ai">para agentes de IA</a> reúne en un '
        "solo lugar el documento de descubrimiento, el esquema OpenAPI, los "
        "flujos de trabajo Arazzo y el endpoint MCP."
    ),
    # -------------------------------------------------------------------- AI
    "ai.title": "Para agentes de IA",
    "ai.description": (
        "Todo lo que un software necesita para usar este escáner sin haber "
        "sido escrito pensando en él: el documento de descubrimiento, el "
        "esquema OpenAPI, los flujos de trabajo Arazzo y el endpoint MCP."
    ),
    "ai.kicker": "Huéspedes automatizados",
    "ai.lede": (
        "Este servicio está pensado para que lo use software que no se "
        "escribió pensando en él. Todo lo que un agente necesita está "
        "publicado, abiertamente, sin necesidad de cuenta: qué puede hacer la "
        "API, cómo se combinan sus llamadas en una tarea, y una forma de "
        "ejecutar esa tarea directamente."
    ),
    "ai.discovery.kicker": "Descubrimiento",
    "ai.discovery.heading": "Empieza desde una sola dirección",
    "ai.discovery.discovery": (
        '<strong>Descubrimiento</strong>: <a href="/.well-known/ai.json">'
        "/.well-known/ai.json</a> nombra todo lo que sigue, con URLs "
        "absolutas. Empieza aquí."
    ),
    "ai.discovery.openapi": (
        '<strong>OpenAPI</strong>: <a href="/openapi.json">/openapi.json</a>, '
        "cada operación con sus códigos de estado reales y las formas de sus "
        "respuestas."
    ),
    "ai.discovery.arazzo": (
        '<strong>Flujos de trabajo Arazzo</strong>: <a href="/arazzo.json">'
        "/arazzo.json</a>, el ciclo de vida de un análisis: enviar, "
        "consultar, detectar la finalización, exportar."
    ),
    "ai.discovery.mcp": (
        "<strong>MCP</strong>: <code>{url}</code>, un endpoint de Model "
        "Context Protocol sobre HTTP en streaming. Herramientas: "
        "<code>scan_instance</code>, <code>scan_instances</code>, "
        "<code>get_scan_result</code>, <code>plan_remediation</code>, "
        "<code>export_scan</code> y <code>erase_instance_data</code>. "
        "<code>scan_instance</code> realiza toda la tarea (envío, espera y "
        "resultado) en una sola llamada. Los prompts nombran las tareas "
        "mismas, como <code>audit_instance</code>, que audita una instancia y "
        "redacta el plan de corrección, y "
        "<code>review_transport_security</code>, que solo examina el "
        "certificado y el saludo TLS. Responde al protocolo en lugar de a un "
        "navegador, así que es una dirección para configurar más que una "
        "página para abrir."
    ),
    "ai.discovery.summary": (
        "Los tres documentos describen un mismo servicio desde tres ángulos: "
        "OpenAPI dice qué puede hacer la API, y Arazzo dice cómo se combinan "
        "esas operaciones en una tarea. Se generan a partir del mismo código "
        "que ejecuta el servidor, así que ninguno puede quedarse "
        "desactualizado sin que se note."
    ),
    "ai.discovery.summary_mcp": (
        "Los tres documentos describen un mismo servicio desde tres ángulos: "
        "OpenAPI dice qué puede hacer la API, Arazzo dice cómo se combinan "
        "esas operaciones en una tarea, y MCP entrega esa tarea a un agente "
        "como una herramienta que puede invocar. Se generan a partir del "
        "mismo código que ejecuta el servidor, así que ninguno puede quedarse "
        "desactualizado sin que se note."
    ),
    "ai.webmcp.kicker": "En el navegador",
    "ai.webmcp.heading": "Usa la página como herramienta",
    "ai.webmcp.intro": (
        "Un navegador compatible con el "
        '<a href="https://webmachinelearning.github.io/webmcp/" '
        'rel="noopener noreferrer">borrador de WebMCP</a> puede descubrir las '
        "acciones de la página abierta. No hace falta configurar otro cliente."
    ),
    "ai.webmcp.landing": (
        "En la página de inicio, <code>scan_opencloud_security</code> pone un "
        "análisis en cola. Su esquema contiene los canales de versión, formatos "
        "de salida y excepciones que ofrece esa página."
    ),
    "ai.webmcp.result": (
        "En una página de resultados, <code>get_scan_result</code> lee el análisis "
        "actual y <code>export_scan_report</code> descarga JSON, CSV, SARIF o PDF "
        "para el uuid que ya se está viendo."
    ),
    "ai.webmcp.boundary": (
        "Cada herramienta del navegador llama a la misma API JSON con "
        "<code>Accept: application/json</code>. Se mantienen la protección SSRF, "
        "los límites, la espera por objetivo, la cola y el aislamiento por uuid."
    ),
    "ai.webmcp.support": (
        "WebMCP todavía es un borrador y los navegadores sin soporte lo ignoran. "
        "Al desactivar MCP en este despliegue también desaparecen las herramientas "
        "del navegador."
    ),
    "ai.clients.kicker": "Configuración",
    "ai.clients.heading": "Conectarlo a un cliente",
    "ai.clients.intro": (
        "La mayoría de las herramientas para agentes aceptan una URL y un "
        "transporte. Este es HTTP en streaming, sin autenticación y sin "
        "cuenta:"
    ),
    "ai.clients.body": (
        "Encontrarás configuraciones completas para Claude Code, Claude "
        "Desktop, GitHub Copilot en VS Code y en la CLI, Cursor, Zed y "
        "Windsurf, contra este despliegue o contra el tuyo propio, en "
        '<a href="{project}/blob/main/docs/mcp.md" '
        'rel="noopener noreferrer">la guía de MCP</a>.'
    ),
    "ai.rules.kicker": "Las reglas",
    "ai.rules.heading": "Las mismas reglas que para todos",
    "ai.rules.body": (
        "Las reglas son las mismas para un agente que para cualquier otra "
        "persona. Un análisis es asíncrono y el uuid es la única forma de "
        "volver a él; un <code>429</code> es una invitación a reducir el "
        "ritmo, no una negativa; y si vas a comprobar más de un puñado de "
        'instancias, por favor <a href="{project}" '
        'rel="noopener noreferrer">ejecuta el escáner tú mismo</a>: es el '
        "mismo código, en tu máquina, sin límites."
    ),
    # -------------------------------- Docker one-liners, on /documentation
    "cli.lede": (
        "Es razonable dudar antes de entregar una dirección al servidor de "
        "un desconocido. No hace falta: esta página es la misma "
        "comprobación, como un único comando en tu propia máquina."
    ),
    "cli.oneliner.kicker": "El comando de una línea",
    "cli.oneliner.heading": "Un comando, nada instalado",
    "cli.oneliner.body": (
        "Eso es todo. Imprime el mismo veredicto que muestra este sitio (la "
        "calificación, el ciclo de vida de la versión, los avisos de "
        "seguridad y cada comprobación fallida) y termina con el código de "
        "estado de Nagios, así que la misma línea funciona en un script, una "
        "canalización o una tarea de cron. No se envía nada a ningún sitio: "
        "el contenedor se comunica con tu instancia y con nadie más."
    ),
    "cli.json.kicker": "Como JSON",
    "cli.json.heading": "El documento de resultado completo",
    "cli.json.body": (
        "Cada número de una página de resultados sale de este documento, "
        'incluido el bloque <code>addresses</code> detrás de la línea '
        "<strong>Resuelto a</strong>: las direcciones IPv4 e IPv6 a las que "
        "apuntaba el nombre mientras se ejecutaba el análisis."
    ),
    "cli.private.kicker": "Tu propia red",
    "cli.private.heading": "Las instancias que este sitio no analizará",
    "cli.private.body": (
        "Un servicio público que analizara direcciones privadas sería un "
        "servicio público que se podría dirigir contra la red interna de "
        "otra persona, así que este lo rechaza. Tu propia máquina no tiene "
        "ese problema: un servidor de pruebas, un nombre que solo conoce tu "
        "resolutor o una instancia que nunca sale de la LAN funcionan todos "
        "desde la línea de comandos."
    ),
    "cli.nodocker.kicker": "¿Sin Docker?",
    "cli.nodocker.heading": "Sin contenedor",
    "cli.nodocker.body": (
        "La comprobación es un programa Python corriente en PyPI, así que "
        "<code>uv</code> o <code>pipx</code> lo descargarán y ejecutarán sin "
        "instalar nada de forma permanente."
    ),
    # ------------------------------------------------ CLI documentation index
    "docs.index.title": "Documentación de la CLI",
    "docs.index.description": (
        "Instala, ejecuta y configura la CLI de check-opencloud-security, con "
        "las guías completas para operadores reunidas en un solo lugar."
    ),
    "docs.index.kicker": "Documentación",
    "docs.index.heading": "Ejecuta el escáner desde tu terminal",
    "docs.index.lede": (
        "La referencia práctica de la CLI, recopilada del README del "
        "proyecto y de las guías bajo <code>docs/</code>. Empieza con un "
        "comando; guarda el resto para cuando la comprobación pase a formar "
        "parte de la monitorización, la integración continua o una flota de "
        "instancias."
    ),
    "docs.index.toc.quickstart": "Inicio rápido",
    "docs.index.toc.commands": "Comandos",
    "docs.index.toc.options": "Opciones útiles",
    "docs.index.toc.configuration": "Configuración",
    "docs.index.toc.monitoring": "Monitorización",
    "docs.index.toc.guides": "Guías completas",
    "docs.index.quickstart.kicker": "Inicio rápido",
    "docs.index.quickstart.heading": "Una comprobación, sin instalar nada",
    "docs.index.quickstart.container": (
        "O usa el contenedor publicado. Ejecuta el mismo complemento y "
        "devuelve el mismo código de salida de Nagios/Icinga:"
    ),
    "docs.index.quickstart.note": (
        "El complemento se comunica directamente con la instancia. No envía "
        "la dirección a este sitio web ni a ningún servicio remoto de "
        "veredictos."
    ),
    "docs.index.commands.kicker": "Dos puntos de entrada",
    "docs.index.commands.heading": "El veredicto y el documento de resultado",
    "docs.index.commands.plugin": (
        "El complemento de monitorización: una línea de alerta, datos de "
        "rendimiento y los códigos de salida estándar <strong>OK</strong>, "
        "<strong>WARNING</strong>, <strong>CRITICAL</strong> y "
        "<strong>UNKNOWN</strong>."
    ),
    "docs.index.commands.scanner": (
        "La biblioteca del escáner como CLI: el documento de resultado JSON "
        "completo para un script, una canalización o una investigación "
        "puntual."
    ),
    "docs.index.options.kicker": "Las opciones del día a día",
    "docs.index.options.heading": "Opciones útiles",
    "docs.index.option.host": (
        "Nombre de host, IP o URL; separados por comas para varias instancias."
    ),
    "docs.index.option.check_hardening": (
        "Incluye las medidas de refuerzo faltantes y las cabeceras de seguridad."
    ),
    "docs.index.option.release_track": (
        "<code>rolling</code>, <code>production</code>, <code>lts</code> o "
        "<code>auto</code>."
    ),
    "docs.index.option.ignore_hardening": (
        "Acepta un hallazgo sin borrar su evidencia; repetible y admite "
        "comodines."
    ),
    "docs.index.option.debug": (
        "Explica de dónde partió la calificación y qué la frenó."
    ),
    "docs.index.option.insecure": (
        "Omite la verificación del certificado para una instancia que controlas."
    ),
    "docs.index.option.thresholds": (
        "Elige los umbrales de calificación que se corresponden con los "
        "estados de monitorización."
    ),
    "docs.index.option.format": "Imprime la salida de Nagios o texto de Prometheus.",
    "docs.index.option.baseline": (
        "Alerta solo sobre hallazgos nuevos o peores que en la ejecución anterior."
    ),
    "docs.index.option.webhook": (
        "Notifica a otro sistema cuando se alcanza el estado configurado."
    ),
    "docs.index.options.manual": (
        "<code>check-opencloud-security --help</code> es el manual "
        'instalado. La <a href="{project}#cli-usage" '
        'rel="noopener noreferrer">tabla completa de opciones</a> incluye '
        "cada valor predeterminado y su variable de entorno <code>COS_</code>."
    ),
    "docs.index.configuration.kicker": "Una sola dirección",
    "docs.index.configuration.heading": "Configuración y prioridad",
    "docs.index.configuration.intro": (
        "Los ajustes pueden provenir de un archivo YAML o JSON, del entorno o "
        "de la línea de comandos. El orden es siempre:"
    ),
    "docs.index.precedence.aria": "Prioridad de configuración, de mayor a menor",
    "docs.index.precedence.cli": "Opción de la CLI",
    "docs.index.precedence.cli.note": "la respuesta explícita para esta ejecución",
    "docs.index.precedence.env": "Entorno",
    "docs.index.precedence.env.note": (
        "<code>COS_*</code>, útil en contenedores y servicios"
    ),
    "docs.index.precedence.file": "Archivo de configuración",
    "docs.index.precedence.file.note": "los valores predeterminados duraderos del operador",
    "docs.index.precedence.default": "Valor predeterminado incorporado",
    "docs.index.precedence.default.note": (
        "la respuesta segura cuando no se especificó nada"
    ),
    "docs.index.configuration.wizard": "Deja que el asistente escriba el primer archivo:",
    "docs.index.configuration.note": (
        "Un archivo que termina en <code>.json</code> es JSON; cualquier "
        "otra extensión es YAML. Los secretos pueden vivir en archivos "
        "separados en lugar de en la línea de comandos."
    ),
    "docs.index.monitoring.kicker": "Ponlo a trabajar",
    "docs.index.monitoring.heading": (
        "Monitorización, automatización y varias instancias"
    ),
    "docs.index.monitoring.nagios": (
        "<strong>Nagios o Icinga:</strong> usa directamente la salida del "
        "complemento; el peor umbral configurado determina el código de "
        "salida."
    ),
    "docs.index.monitoring.fleet": (
        "<strong>Varias instancias:</strong> pasa una lista de hosts "
        "separados por comas, o usa un archivo de configuración por "
        "instancia en cuanto sus ajustes diverjan."
    ),
    "docs.index.monitoring.prometheus": (
        "<strong>Prometheus:</strong> usa <code>--format=prometheus</code> "
        "una vez, o expón el exportador incorporado con "
        "<code>--prometheus-listen-port</code>."
    ),
    "docs.index.monitoring.ci": (
        "<strong>CI:</strong> ejecuta el mismo comando en una canalización; "
        "el código de estado hace que una política incumplida haga fallar "
        "el trabajo sin necesidad de un envoltorio."
    ),
    "docs.index.monitoring.scheduled": (
        "<strong>Comprobaciones programadas:</strong> systemd, cron, "
        "Kubernetes y el rol de Ansible usan todos el mismo flujo de CLI y "
        "configuración."
    ),
    "docs.index.guides.kicker": "Desde el repositorio",
    "docs.index.guides.heading": "Guías completas para operadores",
    "docs.index.guides.lede": (
        "Cada documento fuente tiene aquí su propia página HTML, generada a "
        "partir del Markdown del repositorio y comprobada en CI para "
        "detectar desviaciones."
    ),
    # --------------------------------------------------- generated guide pages
    "docs.guide.kicker": "Documentación de la CLI",
    "docs.guide.english_notice": (
        "Esta guía se genera a partir de la documentación del proyecto y "
        "solo está disponible en inglés. La página que la rodea está "
        "traducida; el texto de abajo no lo está."
    ),
    "docs.guide.toc.heading": "En esta página",
    "docs.guide.toc.aria": "En esta página",
    # ----------------------------------------------------------------- search
    "search.title": "Buscar",
    "search.description": (
        "Busca en la documentación del escáner y en las guías públicas. Los "
        "resultados de análisis nunca se indexan."
    ),
    "search.eyebrow": "Índice estático de la versión",
    "search.heading": "Buscar en el escáner",
    "search.lede": (
        "Solo documentación y guías públicas. El índice se reconstruye con "
        "cada versión; nunca lee el almacén de análisis, las páginas de "
        "resultados, los UUID ni las direcciones enviadas."
    ),
    "search.label": "Buscar en la documentación",
    "search.placeholder": "TLS, Docker, exenciones...",
    "search.submit": "Buscar",
    "search.status.idle": "Introduce un término para buscar en la documentación de esta versión.",
    "search.status.results": "{count} resultado(s) en esta versión.",
    "search.status.empty": "Ninguna documentación pública coincide con esa búsqueda.",
    "search.status.error": "La búsqueda no está disponible temporalmente.",
    # The search manifest: the title and summary an index entry carries, as
    # opposed to the words on the page itself.
    "search.page.index.title": "Analizar una instancia de OpenCloud",
    "search.page.index.summary": (
        "Ejecuta un análisis de seguridad público contra una instancia de "
        "OpenCloud."
    ),
    "search.page.how.title": "Cómo funciona el escáner",
    "search.page.how.summary": (
        "Qué mide el escáner, qué no puede ver, y cómo se gestionan los "
        "resultados."
    ),
    "search.page.grades.title": "Qué significan las calificaciones",
    "search.page.grades.summary": (
        "La escala de calificación de A+ a F y las correcciones que mejoran "
        "cada nivel."
    ),
    "search.page.catalogue.title": "Qué comprueba el escáner",
    "search.page.catalogue.summary": (
        "Cada indicador de refuerzo, cabecera y comprobación TLS del "
        "escáner, y cada vulnerabilidad conocida."
    ),
    "search.page.documentation.title": "Documentación de la CLI",
    "search.page.documentation.summary": (
        "Inicio rápido de línea de comandos, configuración, monitorización y "
        "guías de despliegue."
    ),
    "search.page.api.title": "API",
    "search.page.api.summary": (
        "Envía análisis, consulta resultados, exporta informes y borra los "
        "datos retenidos."
    ),
    "search.page.ai.title": "IA y MCP",
    "search.page.ai.summary": (
        "OpenAPI legible por máquina, Arazzo, descubrimiento, herramientas "
        "MCP y prompts."
    ),
    "search.page.privacy.title": "Privacidad",
    "search.page.privacy.summary": (
        "Retención de resultados, registro de solicitudes, límites de "
        "frecuencia y política sobre terceros."
    ),
    "search.page.about.title": "Acerca de este proyecto",
    "search.page.about.summary": (
        "Por qué existe este escáner de seguridad independiente para OpenCloud."
    ),
    # ------------------------------------------- what a submission is refused for
    # The API answers the English sentence these translate; a browser reads
    # the translation. The SSRF guard names the identifier, this names the
    # sentence, and neither is derived from the other.
    "error.unsupported_fields": (
        "Este servicio no acepta {fields}. El análisis se ejecuta únicamente "
        "con ajustes del lado del servidor."
    ),
    "error.rate_limit.client": (
        "Son muchos análisis desde tu red en poco tiempo. Espera un minuto e "
        "inténtalo de nuevo."
    ),
    "error.rate_limit.target": (
        "Esa instancia se analizó hace muy poco. Por favor, espera unos minutos."
    ),
    "error.target.invalid": "Esa dirección no se puede analizar.",
    "error.target.empty": "Introduce la dirección de la instancia de OpenCloud que quieres analizar.",
    "error.target.too_long": "Esa dirección es demasiado larga.",
    "error.target.characters": (
        "Esa dirección contiene caracteres que un nombre de host no puede tener."
    ),
    "error.target.unparsed": "No se pudo interpretar esa dirección.",
    "error.target.scheme": "Solo se pueden analizar destinos http:// y https://.",
    "error.target.credentials": "No se aceptan credenciales dentro de la dirección.",
    "error.target.address_only": (
        "Introduce solo la dirección base de la instancia. Se acepta una "
        "subcarpeta simple, pero no consultas, fragmentos, parámetros ni "
        "recorridos de ruta."
    ),
    "error.target.port": "Esa dirección tiene un puerto no válido.",
    "error.target.no_host": "Esa dirección no tiene nombre de host.",
    "error.target.hostname_shape": (
        "Eso no es un nombre de host que este servicio pueda analizar."
    ),
    "error.target.unresolved": "Ese nombre de host no se resuelve.",
    "error.target.hostname_long": "Ese nombre de host es demasiado largo.",
    "error.target.internal": "No se pueden analizar direcciones locales ni internas.",
    "error.target.private": (
        "Esa dirección apunta a una red privada, de loopback o de enlace "
        "local, y este servicio no la analizará."
    ),
    # ----------------------------------------------------------- result page
    "result.title": "Resultados del análisis",
    "result.description": (
        "El resultado de un análisis público, legible únicamente con su "
        "propio identificador."
    ),
    "result.kicker": "Informe de campo",
    "result.heading": "Resultado del análisis",
    "result.track.title": "El canal de publicación contra el que se calificó este análisis",
    "result.track.label": "Canal {track}",
    "result.another": "Analizar otra instancia",
    "result.progress.kicker": "En curso",
    "result.progress.queued.title": "Esperando un proceso de análisis disponible",
    "result.progress.queued.detail": (
        "Todos los procesos están ocupados en este momento. Tu análisis "
        "conserva su lugar en la fila y comenzará en cuanto uno quede libre."
    ),
    "result.progress.running.title": "Analizando la instancia",
    "result.progress.running.detail": (
        "Leyendo lo que publica la instancia: versión, capacidades, "
        "certificado, cabeceras y los endpoints que expone sin iniciar sesión."
    ),
    "result.progress.step.queued": "En cola",
    "result.progress.step.running": "En ejecución",
    "result.progress.step.done": "Resultado",
    "result.progress.noscript": (
        "Esta página se actualiza sola mediante JavaScript. Sin él, recarga "
        "la página en unos segundos para ver el resultado."
    ),
    "result.progress.queue.position": (
        "Análisis en cola. Posición en la fila: n.º {position} de {length}."
    ),
    "result.progress.queue.next": "Análisis en cola. Eres el siguiente.",
    "result.progress.queue.waiting": "Esperando a que un proceso de análisis lo recoja.",
    "result.progress.done.title": "Informe listo",
    "result.progress.done.detail": "La calificación ya está lista. Abriendo el informe.",
    "result.progress.failed.title": "Análisis finalizado",
    "result.progress.failed.detail": (
        "El análisis no se pudo completar. Abriendo lo que se obtuvo."
    ),
    "result.failed.fallback": "El análisis no se pudo completar.",
    "result.failed.body": (
        "No se calificó nada, porque no se obtuvo nada utilizable. Comprueba "
        "que la dirección sea correcta, que la instancia sea accesible desde "
        "internet públicamente, y que se trate de una instancia de OpenCloud."
    ),
    "result.document.kicker": "Documento de resultado",
    "result.document.heading": "Documento de resultado",
    "result.document.lede": (
        "El mismo documento que evalúan la comprobación de línea de comandos "
        "y el complemento de Nagios."
    ),
    "result.verdict.kicker": "Veredicto",
    "result.verdict.heading": "Calificación general",
    "result.verdict.dial": "Calificación {label}, {rating} de 5",
    "result.facts.instance": "Instancia",
    "result.facts.resolved": "Resuelto a",
    "result.facts.ipv6.heading": "Accesibilidad IPv6",
    "result.facts.ipv6.note": (
        "No comprobada - este despliegue no tiene conectividad IPv6 "
        "saliente, así que solo se anota aquí en lugar de penalizar la "
        "instancia."
    ),
    "result.facts.product": "Producto",
    "result.facts.track": "Canal de publicación",
    "result.facts.track.unknown": "desconocido",
    "result.facts.eol_tag": "Fin de vida útil",
    "result.facts.schedule": "Calendario de versiones",
    "result.facts.schedule.stale": (
        "{version} es más reciente que esta copia del calendario de "
        "versiones de OpenCloud, así que el calendario probablemente esté "
        "desactualizado. Esto no se cuenta en contra de la instancia -"
    ),
    "result.facts.schedule.stale_generated": (
        "{version} es más reciente que esta copia del calendario de "
        "versiones de OpenCloud, generada el {generated}, así que el "
        "calendario probablemente esté desactualizado. Esto no se cuenta en "
        "contra de la instancia -"
    ),
    "result.facts.schedule.link": "consulta la página publicada del ciclo de vida",
    "result.facts.signin": "Inicio de sesión",
    "result.facts.signin.external": "Proveedor externo",
    "result.facts.signin.upstream_tag": "upstream",
    "result.facts.signin.version_unavailable": "versión no expuesta",
    "result.facts.signin.advisories": "consultar avisos de seguridad",
    "result.facts.signin.builtin": "Proveedor de identidad integrado",
    "result.facts.signin.none": "No detectado -",
    "result.facts.signin.link": "cómo se configura el inicio de sesión de OpenCloud",
    "result.facts.proxy": "Proxy inverso",
    "result.facts.proxy.detected": "Detectado",
    "result.facts.office": "Office",
    "result.facts.calendar": "Calendario",
    "result.facts.calendar.detected": "Algo responde en la ruta CalDAV",
    "result.facts.newest": "Versión más reciente",
    "result.facts.score": "Puntuación",
    "result.facts.score.value": "{rating} de 5",
    "result.counter.critical": "Crítico",
    "result.counter.warning": "Advertencia",
    "result.counter.info": "Información",
    "result.counter.advisories": "Avisos",
    "result.counter.passed": "Superadas",
    "result.verdict.why": "Por qué esta calificación:",
    "result.verdict.caveat": (
        "Una calificación indica que las comprobaciones de abajo se "
        "superaron, no que la instancia sea segura. Este análisis no es "
        "exhaustivo: solo ve lo que la instancia muestra a un visitante "
        'anónimo. <a href="#scan-limits">Lo que no puede ver</a>.'
    ),
    "result.fix": "Solución:",
    "result.documentation": "Documentación",
    "result.explain.title": "Qué significa esta comprobación",
    "result.plan.kicker": "Plan de corrección",
    "result.plan.heading": "Qué te lleva a {label}",
    "result.plan.then": "luego {label}",
    "result.plan.still": "sigue en {label}",
    "result.plan.note": (
        "El orden es el que da resultado antes, y la calificación junto a "
        "cada paso es la que se obtendría una vez completado ese paso y "
        "todos los anteriores. Los hallazgos de la misma gravedad comparten "
        "un único límite, así que la calificación solo cambia cuando "
        "desaparece el último de ellos; por eso un paso puede ser necesario "
        "y aun así no prometer nada por sí solo."
    ),
    "result.plan.blocked.heading": "Frenando la calificación, y sin solución posible",
    "result.plan.blocked.note": (
        "OpenCloud codifica estos valores de forma fija, así que ningún "
        "ajuste los alcanza. Son la razón por la que el plan anterior se "
        "detiene donde lo hace."
    ),
    "result.eol.alert": (
        "Esta versión ya no recibe correcciones de seguridad. Nada más en "
        "esta página puede elevar la calificación hasta que se actualice."
    ),
    "result.advisories.kicker": "Avisos",
    "result.advisories.heading": "Avisos conocidos para esta versión",
    "result.advisories.lede": (
        "Avisos publicados cuyo rango afectado incluye {version}."
    ),
    "result.advisories.fallback_id": "aviso",
    "result.advisories.unrated": "sin calificar",
    "result.advisories.no_summary": "No se ha publicado ningún resumen.",
    "result.advisories.read": "Leer el aviso",
    "result.findings.kicker": "Hallazgos",
    "result.findings.heading": "Comprobaciones que fallaron",
    "result.findings.lede": (
        "Cada uno limita la calificación al nivel que permite su gravedad. "
        "Corrige primero los críticos: son los que más frenan la puntuación."
    ),
    "result.findings.allclear.tag": "Todo en orden",
    "result.findings.allclear.body": (
        "Todas las comprobaciones que ejecuta este escáner se superaron en "
        "esta instancia."
    ),
    "result.hardening.kicker": "Refuerzo",
    "result.hardening.heading": "Refuerzos que vale la pena añadir",
    "result.hardening.lede": (
        "Ajustes que no están activados. Ninguno de ellos es una "
        "vulnerabilidad activa; cada uno elimina una vía de entrada."
    ),
    "result.hardening.tag": "refuerzo",
    "result.header.tag": "cabecera",
    # ------------------------------------------------- configuration fragment
    "result.fragment.kicker": "La corrección, escrita",
    "result.fragment.heading": "Pegue esto en su configuración",
    "result.fragment.lede": (
        "Los hallazgos de arriba, en la sintaxis del archivo que debe "
        "cambiar. Elija dónde se configura su instancia."
    ),
    "result.fragment.caution": (
        "Lea la línea «Corrección» de cada hallazgo antes de pegar. Estos son "
        "los valores que buscan las comprobaciones, no una revisión de lo que "
        "necesita su despliegue."
    ),
    "result.fragment.picker": "Formato de configuración",
    "result.fragment.file": "Va en {name}.",
    "result.fragment.copy": "Copiar",
    "result.fragment.copied": "Copiado",
    "result.fragment.copy_failed": "No se pudo copiar",
    "result.fragment.nothing": (
        "Aquí no se ajusta nada de esta forma. Lo que queda abierto "
        "corresponde a {flavours}."
    ),
    "result.fragment.elsewhere": (
        "Estos se corrigen en otro sitio - corresponden a {flavours}:"
    ),
    "result.fragment.undecided": (
        "Estos no tienen ningún valor que pegar: el correcto es una decisión "
        "sobre este despliegue, y la línea «Corrección» del hallazgo es toda "
        "la respuesta."
    ),
    # ------------------------------------------------------------ scan again
    "result.rescan": "Analizar de nuevo",
    "result.rescan.ready": "Esta instancia se puede analizar de nuevo.",
    "result.rescan.wait": "Se podrá analizar de nuevo en {countdown}.",
    "result.rescan.note": (
        "Mismo objetivo, mismas exenciones, mismo canal de versiones - para "
        "que el próximo resultado sea comparable con este. La espera es lo "
        "que mantiene en pie a este pequeño servicio; el escáner es de código "
        "abierto y funciona en su propia máquina sin límite alguno:"
    ),
    "result.rescan.self_host": "ejecútelo usted mismo",
    "result.excluded.kicker": "Excluido",
    "result.excluded.heading": "Reportado, pero no contabilizado",
    "result.excluded.waived.heading": "Pediste ignorar estos",
    "result.excluded.waived.note": "Siguieron fallando. Simplemente no frenaron la calificación.",
    "result.excluded.unfixable.heading": "Nadie puede cambiar esto",
    "result.excluded.unfixable.note": (
        "OpenCloud codifica estas opciones de forma fija, así que se leen "
        "igual en cualquier instancia existente. Se muestran por "
        "completitud y quedan excluidas de la calificación."
    ),
    "result.scope.kicker": "Alcance",
    "result.scope.heading": "Lo que este análisis no puede ver",
    "result.scope.body": (
        "Todo lo anterior se leyó sin iniciar sesión, que es precisamente el "
        "objetivo y también el límite. <strong>La ausencia de un hallazgo no "
        "es prueba de seguridad</strong>, y la calificación más alta que "
        "puede dar esta página no es una afirmación de que la instancia sea "
        "segura, solo de que nada de lo comprobado aquí falló. Categorías "
        "enteras quedan totalmente fuera del alcance de un análisis no "
        "autenticado: el sistema operativo y sus paquetes, el entorno de "
        "ejecución de contenedores, la configuración propia del proxy "
        "inverso, las copias de seguridad y sus restauraciones, el "
        "almacenamiento detrás de la instancia, el manejo de secretos y "
        "claves, las cuentas, las contraseñas y el inicio de sesión "
        "multifactor, los permisos de los recursos compartidos existentes, "
        "la cadena de suministro del software, y cualquier cosa que solo se "
        "muestre a un usuario que ha iniciado sesión. Lo mismo ocurre con "
        "estas dos, que parece que deberían ser visibles y no lo son:"
    ),
    "result.scope.audit": (
        "<strong>Registro de auditoría.</strong> El servicio de auditoría de "
        "OpenCloud solo consume el bus de eventos interno; no publica ningún "
        "endpoint ni aparece en ningún documento no autenticado, así que no "
        "hay forma de determinar desde fuera si se está ejecutando. No se "
        "comprueba."
    ),
    "result.scope.integrations": (
        "<strong>Si una integración de ofimática o calendario está "
        "configurada <em>correctamente</em>.</strong> Esta página solo "
        "informa de que hay un proveedor de aplicaciones registrado, o de "
        "que algo responde en la ruta CalDAV. Las reglas de compartición, "
        "los secretos WOPI y la configuración propia del segundo servicio "
        "viven todos detrás de un inicio de sesión y no se comprueban."
    ),
    "result.tls.kicker": "Transporte",
    "result.tls.heading": "Seguridad del transporte",
    "result.tls.lede": (
        "Lo que dijo la capa TLS antes de intercambiar un solo byte de HTTP. "
        "Los hallazgos anteriores ya valoran esto; aquí está la medición que "
        "hay detrás."
    ),
    "result.tls.protocol": "Protocolo",
    "result.tls.bits": "({bits} bits)",
    "result.tls.deprecated": "Versiones obsoletas",
    "result.tls.deprecated.accepted": "Todavía aceptadas: {list}",
    "result.tls.deprecated.refused": "Rechazadas: {list}",
    "result.tls.chain": "Cadena",
    "result.tls.chain.trusted": "De confianza",
    "result.tls.chain.not_established": "No establecida",
    "result.tls.chain.not_trusted": "No es de confianza",
    "result.tls.chain.incomplete_note": "- sin ruta hasta una raíz pública",
    "result.tls.issued_to": "Emitido para",
    "result.tls.unnamed": "sin nombre",
    "result.tls.issued_by": "Emitido por",
    "result.tls.unknown": "desconocido",
    "result.tls.valid_for": "Válido para",
    "result.tls.validity": "Validez",
    "result.tls.validity.range": "{start} a {end}",
    "result.tls.validity.expired": "- caducó hace {days} día(s)",
    "result.tls.validity.remaining": "- quedan {days} día(s)",
    "result.tls.lifetime": "Emitido por un período de",
    "result.tls.lifetime.days": "{days} día(s)",
    "result.tls.ocsp": "OCSP stapling",
    "result.tls.ocsp.stapled": "Se adjunta una respuesta de revocación",
    "result.tls.ocsp.not_stapled": "No adjunta",
    "result.tls.ocsp.undetermined": "No determinado",
    "result.raw.kicker": "Datos en bruto",
    "result.raw.heading": "Detalles técnicos",
    "result.raw.lede": "El documento de resultado completo, tal como lo ve el complemento.",
    "result.raw.summary": "Mostrar el JSON en bruto",
    "result.export.kicker": "Exportar",
    "result.export.heading": "Llévate este resultado",
    "result.export.lede": (
        "El mismo análisis, presentado de cuatro formas distintas. Cada una "
        "se genera cuando la solicitas y desaparece junto con el propio "
        "análisis."
    ),
    "result.export.pdf": "Informe en PDF",
    "result.export.pdf.hint": "Para un ticket, una revisión o una copia impresa.",
    "result.export.csv": "CSV",
    "result.export.csv.hint": "Una fila por hallazgo, para una hoja de cálculo.",
    "result.export.sarif": "SARIF",
    "result.export.sarif.hint": "Para un panel de análisis de código.",
    "result.export.json": "JSON",
    "result.export.json.hint": "El documento en bruto que evalúa el complemento.",
    "result.export.passed.heading": "Lo que ya ha pasado",
    "result.export.passed.note": (
        "Estas comprobaciones salieron limpias, así que no están en el plan de arriba."
    ),
    "result.share.kicker": "Compartir",
    "result.share.heading": "Compartir este informe",
    "result.share.lede": (
        "Por correo o desde tu propio portapapeles. Nada pasa por este "
        "servicio y no se pide ayuda a ninguna otra empresa."
    ),
    "result.share.warning": (
        "La dirección de esta página es lo único que la protege: quien la "
        "tenga puede leer el informe hasta que caduque. Publicarla en un canal "
        "la comparte con todos los que estén allí, y con todo lo que consulte "
        "enlaces para generar una vista previa. Copia el resumen cuando lo que "
        "importa son los hallazgos."
    ),
    "result.share.email": "Compartir por correo",
    "result.share.email.hint": (
        "Abre tu propio cliente de correo con el mensaje preparado. Nada sale "
        "de tu navegador hasta que lo envías."
    ),
    "result.share.email.subject": "Informe de seguridad de OpenCloud para {target}",
    "result.share.email.body": (
        "Este es el informe de seguridad de nuestra instancia de OpenCloud:\n\n"
        "{url}\n\n"
        "Este enlace es lo que da acceso al informe, así que trátalo como una "
        "contraseña. Caduca por sí solo y después la página deja de existir."
    ),
    "result.share.link": "Copiar enlace",
    "result.share.link.hint": (
        "La dirección de esta página. Quien la reciba puede abrir el informe."
    ),
    "result.share.summary": "Copiar resumen",
    "result.share.summary.hint": (
        "Los hallazgos como texto, sin ningún enlace. Lo más seguro para pegar "
        "en un canal de chat."
    ),
    "result.share.summary.body": (
        "Informe de seguridad de OpenCloud - {domain}\n"
        "Nota {label} ({rating} de 5)\n"
        "Críticos {critical} | Avisos {warning} | Info {info} | "
        "Alertas {advisories} | Superados {passed}\n"
        "Medido con check-opencloud-security."
    ),
    "result.share.done": "Copiado",
    "result.share.failed": "No se ha podido copiar",
    "result.share.fallback": "La dirección de este informe:",
    "result.feedback.prompt": "¿Crees que el análisis se ha equivocado?",
    "result.feedback.link": "Informa de un falso positivo o un falso negativo",
    "result.expiry.one": (
        "Esta página caduca en aproximadamente 1 minuto; a partir de "
        "entonces el enlace deja de funcionar y el resultado desaparece."
    ),
    "result.expiry.many": (
        "Esta página caduca en aproximadamente {minutes} minutos; a partir "
        "de entonces el enlace deja de funcionar y el resultado desaparece."
    ),
    # ----------------------------------------- transport facts beside the grade
    "tls.fact.protocol": "Versión de TLS",
    "tls.fact.protocol.detail": "también acepta {list}",
    "tls.fact.expiry": "El certificado caduca",
    "tls.fact.expiry.expired": "caducó hace {days} día(s)",
    "tls.fact.expiry.remaining": "quedan {days} día(s)",
    "tls.fact.chain": "Cadena",
    "tls.fact.chain.incomplete": "Incompleta",
    "tls.fact.chain.incomplete.detail": "sin ruta hasta una raíz pública",
    "tls.fact.chain.untrusted": "No es de confianza",
    "tls.fact.chain.untrusted.detail": "autofirmado, o de una autoridad desconocida",
    "tls.fact.chain.unknown": "No establecida",
    "tls.fact.chain.unknown.detail": "el saludo TLS nunca llegó al certificado",
    "tls.fact.chain.ok": "Completa y de confianza",
}
