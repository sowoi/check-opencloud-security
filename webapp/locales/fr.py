"""The French translation of :mod:`webapp.locales.en`."""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    # ---------------------------------------------------------------- site
    # --------------------------------------------- l'espace d'exploitation
    "admin.title": "Espace d'exploitation",
    "admin.description": "État du service, données de référence et journal d'audit.",
    "admin.kicker": "Exploitation",
    "admin.band": "Espace d'exploitation - connecté en tant que {user}",
    "admin.band.signout": "Se déconnecter",
    "admin.lede": (
        "Ce que fait cette installation, ce qu'elle sait, et les deux mises à "
        "jour que le worker exécute une fois par jour. Rien ici ne peut être "
        "interrogé au sujet d'un scan particulier."
    ),
    "admin.noscript": (
        "Les valeurs ci-dessus sont remplies par JavaScript. Sans lui, recharge "
        "la page pour voir les valeurs actuelles ; les deux boutons "
        "fonctionnent toujours."
    ),
    "admin.state.kicker": "Maintenant",
    "admin.state.heading": "État du service",
    "admin.state.lede": (
        "Des compteurs et des limites configurées. Aucune adresse scannée, "
        "aucun uuid et aucune adresse de client n'y figure, parce que rien de "
        "tout cela n'est conservé là où cette vue pourrait le lire."
    ),
    "admin.state.worker": "Worker",
    "admin.state.worker.up": "En marche",
    "admin.state.worker.down": "Ne répond pas",
    "admin.state.worker.unknown": "Impossible à déterminer",
    "admin.state.store.down": (
        "Le stockage ne répond pas - impossible de lire le battement"
    ),
    "admin.state.queue": "{depth} en file, {workers} workers",
    "admin.state.ratelimit": "Limite de requêtes",
    "admin.state.ratelimit.value": "{limit} par {window}s",
    "admin.state.cooldown.value": "{seconds}s par cible",
    "admin.state.schedule": "Calendrier des versions",
    "admin.state.advisories": "Avis de sécurité",
    "admin.state.checked": "vérifié {when}",
    "admin.state.never": "jamais",
    "admin.state.unknown": "inconnu",
    "admin.state.age.seconds": "Lu il y a {seconds}s",
    "admin.state.age.minutes": "Lu il y a {minutes}m",
    "admin.state.age.waiting": "En attente de la première lecture",
    "admin.state.stale": (
        "Le service n'a pas répondu depuis un moment. Ce qui précède est la "
        "dernière lecture qu'il a donnée, pas forcément l'état actuel."
    ),
    "admin.state.refresh": "Relire",
    "admin.state.copy": "Copier le diagnostic",
    "admin.state.copy.done": "Copié",
    "admin.state.copy.failed": "Copie impossible",
    "admin.surfaces.kicker": "Exposition",
    "admin.surfaces.heading": "Ce que propose ce déploiement",
    "admin.surfaces.lede": (
        "Les réglages avec lesquels ce processus a démarré, ceux-là mêmes que "
        "rapporte le document de diagnostic. Aucun ne change sans "
        "redémarrage, aucun n'est donc interrogé."
    ),
    "admin.surfaces.on": "Activé",
    "admin.surfaces.off": "Désactivé",
    "admin.surfaces.mcp": "Point d'accès pour agents sur /mcp",
    "admin.surfaces.mcp.guarded": (
        "Un jeton de l'émetteur configuré est exigé."
    ),
    "admin.surfaces.mcp.open": (
        "Aucun jeton n'est exigé : tout agent capable de l'atteindre peut "
        "mobiliser les workers de ce service."
    ),
    "admin.surfaces.docs": "Pages d'API navigables sur /docs",
    "admin.surfaces.docs.contract": (
        "Les désactiver masque les pages, pas le contrat : /openapi.json, "
        "/arazzo.json et /.well-known/ai.json restent publics."
    ),
    "admin.surfaces.indexed": "Trouvable par les moteurs de recherche",
    "admin.surfaces.private": "Analyses d'adresses réseau privées",
    "admin.surfaces.private.found": (
        "Autorisé sur un déploiement qui demande à être indexé : qui trouve "
        "ce service peut le pointer sur le réseau où il se trouve."
    ),
    "admin.surfaces.private.estate": (
        "Autorisé, ce qui est précisément l'objet d'un déploiement qui "
        "analyse son propre parc."
    ),
    "admin.surfaces.encrypt": "Résultats chiffrés au repos",
    "admin.surfaces.audit": "Journal d'audit",
    "admin.surfaces.audit.file": (
        "Écrit dans un fichier qui survit au conteneur."
    ),
    "admin.surfaces.audit.memory": (
        "Un anneau de {count} enregistrements en mémoire de ce processus, et "
        "rien sur disque."
    ),
    "admin.surfaces.targets": "Cibles enregistrées en clair",
    "admin.actions.kicker": "Données de référence",
    "admin.actions.heading": "Mettre à jour ce sur quoi la note repose",
    "admin.actions.lede": (
        "Les deux mêmes mises à jour que le worker exécute chaque jour, avec "
        "les mêmes règles : un calendrier qui a perdu une ligne de versions est "
        "refusé, une base d'avis ne fait qu'en gagner, et une récupération qui "
        "échoue ne change rien."
    ),
    "admin.actions.schedule": "Synchroniser le calendrier",
    "admin.actions.schedule.hint": "Relit la page de cycle de vie publiée.",
    "admin.actions.advisories": "Chercher des avis",
    "admin.actions.advisories.hint": "Interroge le flux d'avis sur les nouvelles entrées.",
    "admin.outcome.updated": "Mis à jour. Le nouveau document est utilisé.",
    "admin.outcome.unchanged": "Déjà à jour - rien n'a changé.",
    "admin.outcome.rejected": (
        "Refusé : ce qui a été récupéré n'a pas passé les contrôles, les "
        "données précédentes restent donc en service."
    ),
    "admin.outcome.failed": "Récupération impossible. Rien n'a changé.",
    "admin.outcome.disabled": "Cette mise à jour est désactivée dans la configuration de cette installation.",
    "admin.outcome.cooldown": "Vient de s'exécuter. Réessaie dans {seconds}s.",
    "admin.probe.action": "Tester les sources",
    "admin.probe.hint": (
        "Lit les deux sources et rapporte ce qu'une mise à jour en ferait. "
        "Rien n'est enregistré."
    ),
    "admin.probe.schedule": "Calendrier des versions : {answer}",
    "admin.probe.advisories": "Avis : {answer}",
    "admin.probe.usable": "lu, et une mise à jour l'accepterait",
    "admin.probe.rejected": "lu, mais les contrôles le refuseraient",
    "admin.probe.unreadable": "illisible - injoignable, ou plus dans la forme attendue",
    "admin.probe.disabled": "non vérifié - cette mise à jour est désactivée",
    "admin.search.kicker": "Index de recherche",
    "admin.search.heading": "L'index livré est-il encore à jour",
    "admin.search.lede": (
        "L'index est construit au moment de la publication et livré en lecture "
        "seule : cette vue rend compte plutôt que de reconstruire. Elle compare "
        "les pages, les langues et la version pour laquelle il a été généré - "
        "pas le corps du texte, que seul le générateur sait extraire."
    ),
    "admin.search.fresh": "À jour",
    "admin.search.stale": "Périmé",
    "admin.search.detail.ok": "Chaque page et chaque langue est indexée pour cette version.",
    "admin.search.detail.release": "Généré pour {built}, version en service {running}.",
    "admin.search.detail.missing": "Non indexé : {list}.",
    "admin.search.detail.changed": "{count} titres ou résumés ont changé depuis sa génération.",
    "admin.search.detail.unreadable": "L'index n'a pas pu être lu.",
    "admin.search.fix": (
        "Un index périmé est repris par le workflow de publication, qui le "
        "régénère et le valide. Il n'y a rien à presser ici."
    ),
    "admin.audit.kicker": "Audit",
    "admin.audit.heading": "Le journal, au fil de son écriture",
    "admin.audit.lede": (
        "Demandes de scan, refus et limites atteintes, au moment où ils se "
        "produisent. Suivre le journal ouvre une connexion ; rien n'est "
        "transmis tant que tu ne le demandes pas."
    ),
    "admin.audit.privacy": (
        "Une adresse de client est un HMAC tronqué sous un sel que ce processus "
        "détient, et rien ne permet d'en revenir à une adresse. Cette vue ne "
        "peut pas montrer plus que ce que le journal a décidé de noter."
    ),
    "admin.audit.replicas": (
        "Cette installation ne tient pas de fichier d'audit : ces "
        "enregistrements viennent de la mémoire du seul processus qui a "
        "répondu - avec plusieurs répliques, c'est une partie du journal et non "
        "sa totalité."
    ),
    "admin.audit.follow": "Suivre",
    "admin.audit.stop": "Arrêter",
    "admin.audit.clear": "Vider",
    "admin.audit.empty": "Rien pour l'instant.",
    "admin.audit.closed": (
        "La connexion a atteint sa limite de {minutes} minutes et le service "
        "l'a fermée. Rien n'a été perdu jusque-là ; « Suivre » en ouvre une "
        "autre."
    ),
    "admin.audit.disabled": (
        "Cette installation ne tient pas de journal d'audit, il n'y a donc rien "
        "à suivre. COS_WEB_AUDIT_LOG l'active."
    ),
    "admin.audit.state.off": "Pas de suivi",
    "admin.audit.state.live": "En direct",
    "admin.audit.state.reconnecting": "Reconnexion",
    "admin.audit.state.unsupported": "Non pris en charge par ce navigateur",
    "admin.audit.state.closed": "Fermée par le service",
    "admin.audit.state.disabled": "Non tenu",
    "site.og_image_alt": (
        "OpenCloud Security Scan - vérifiez la sécurité d'une instance en "
        "détectant les vulnérabilités connues, le durcissement manquant et les "
        "en-têtes de sécurité faibles"
    ),
    # ------------------------------------------------------- header chrome
    "chrome.skip_to_content": "Passer au contenu",
    "chrome.brand": "Analyse de sécurité pour OpenCloud",
    "chrome.menu": "Menu",
    "chrome.nav.primary": "Principal",
    "chrome.nav.secondary": "Secondaire",
    "chrome.search.label": "Rechercher dans la documentation",
    "chrome.search.placeholder": "Rechercher",
    "chrome.theme.toggle": "Changer le thème de couleur",
    "chrome.back_to_top": "Retour en haut",
    "nav.new_scan": "Nouvelle analyse",
    "nav.how_it_works": "Fonctionnement",
    "nav.grades": "Notes",
    "nav.catalogue": "Catalogue",
    "nav.docs": "Docs",
    "nav.search": "Rechercher",
    "nav.api": "API",
    "nav.ai": "IA",
    "nav.privacy": "Confidentialité",
    "nav.about": "À propos",
    # --------------------------------------------------- language switcher
    "lang.region": "Langue",
    "lang.label": "Langue de la page",
    "lang.apply": "Changer de langue",
    "lang.note": (
        "L'analyse elle-même reste inchangée ; seule cette page est traduite."
    ),
    # ------------------------------------------------------------- footer
    "footer.note.title": "Un service discret, par conception.",
    "footer.note.body": (
        "Les analyses sont exécutées depuis ce serveur vers l'adresse que vous "
        "saisissez. Les résultats vivent en mémoire pendant {minutes} minutes, "
        "puis disparaissent. Construit sur le scanner "
        "<code>check-opencloud-security</code> - aucun traceur, aucun compte, "
        "aucune analyse d'audience."
    ),
    "footer.note.run_yourself": "Exécutez-le vous-même",
    "footer.version.title": "La version du scanner qui a produit ces résultats",
    "footer.version.label": "Backend v{version}",
    "footer.legal.scope": (
        "<strong>Ce contrôle n'est pas exhaustif, et une bonne note n'est pas un "
        "certificat.</strong> Il lit ce qu'une instance OpenCloud accessible "
        "publiquement montre à un visiteur anonyme : sa version, les avis de "
        "sécurité concernant cette version, son transport, ses en-têtes et un "
        "ensemble de paramètres visibles sans connexion. Un &ldquo;A&rdquo; "
        "signifie qu'aucun de ces éléments n'a posé problème - pas que "
        "l'instance est sécurisée. Tout ce qui se trouve derrière la connexion, "
        "le serveur sur lequel elle tourne, le réseau qui l'entoure, les "
        "données qu'elle contient et les personnes disposant d'un compte sont "
        "hors de portée de toute analyse non authentifiée. Considérez le "
        "résultat comme un élément parmi d'autres, jamais comme un audit de "
        "sécurité ou un test d'intrusion."
    ),
    "footer.legal.trademark": (
        "Il s'agit d'un projet communautaire indépendant. Il n'est pas affilié "
        "à OpenCloud GmbH et n'est ni recommandé ni pris en charge par cette "
        "société. &ldquo;OpenCloud&rdquo;, le logo OpenCloud et toutes les "
        "marques associées sont la propriété de leurs détenteurs respectifs et "
        "ne sont utilisés ici que pour indiquer quel logiciel cet outil "
        "vérifie."
    ),
    # --------------------------------------------------- the contents list
    "toc.heading": "Sur cette page",
    "toc.aria": "Sur cette page",
    # --------------------------------------------------------- cross-links
    "pagenav.kicker": "À lire aussi",
    "pagenav.aria": "En savoir plus sur ce service",
    "pagenav.how.title": "Comment fonctionne l'analyse",
    "pagenav.how.blurb": (
        "Ce qui est testé, et les quatre étapes entre le bouton et la note."
    ),
    "pagenav.grades.title": "Ce que signifient les notes",
    "pagenav.grades.blurb": (
        "Chaque échelon de A+ à F, ce qui plombe une note et comment la faire "
        "remonter."
    ),
    "pagenav.catalogue.title": "Ce que le scanner vérifie",
    "pagenav.catalogue.blurb": (
        "Chaque indicateur de durcissement, chaque en-tête et vérification "
        "TLS, et chaque vulnérabilité connue - indépendamment d'une analyse "
        "particulière."
    ),
    "pagenav.docs.title": "Documentation en ligne de commande",
    "pagenav.docs.blurb": (
        "Installez, configurez et automatisez le scanner depuis un terminal."
    ),
    "pagenav.api.title": "Analyser depuis un script",
    "pagenav.api.blurb": (
        "L'API JSON, les limites d'utilisation raisonnable et le schéma OpenAPI."
    ),
    "pagenav.ai.title": "Pour les agents IA",
    "pagenav.ai.blurb": (
        "Découverte, OpenAPI, flux de travail Arazzo et le point de terminaison "
        "MCP."
    ),
    "pagenav.privacy.title": "Ce que ce serveur conserve",
    "pagenav.privacy.blurb": (
        "En mémoire, pendant {minutes} minutes, et ce que le journal omet."
    ),
    "pagenav.about.title": "À propos d'OpenCloud",
    "pagenav.about.blurb": (
        "La plateforme que ceci contrôle, et pourquoi ce projet en est "
        "indépendant."
    ),
    "pagenav.cta.title": "Analyser une instance",
    "pagenav.cta.blurb": (
        "Retour au formulaire. Quelques secondes suffisent, sans inscription."
    ),
    # ---------------------------------------------------------------- 404
    "notfound.title": "Rien ici",
    "notfound.description": (
        "L'adresse n'existe pas, ou l'analyse qu'elle désignait a déjà expiré."
    ),
    "notfound.kicker": "Introuvable",
    "notfound.lede": (
        "Soit l'adresse n'existe pas, soit il s'agissait d'une analyse et cette "
        "analyse a disparu : les résultats sont conservés pendant {minutes} "
        "minutes puis supprimés, si bien qu'un lien reçu plus tôt dans la "
        "journée ne s'ouvrira plus. Un identifiant qui n'a jamais existé se "
        "présente exactement de la même façon ici - ce service ne peut pas vous "
        "dire lequel des deux, et ne cherche délibérément pas à le faire."
    ),
    "notfound.action": "Lancer une nouvelle analyse",
    # ------------------------------------------------------- landing page
    "index.title": "Analyser une instance OpenCloud",
    "index.description": (
        "Vérifiez une instance OpenCloud à la recherche de vulnérabilités "
        "connues, de durcissement manquant et d'en-têtes de sécurité faibles. "
        "Gratuit, indépendant, et rien n'est conservé."
    ),
    "index.eyebrow": "Indépendant &middot; isolé &middot; rien n'est conservé",
    "index.headline": (
        'Quel est le niveau de sécurité de votre <em class="swash">instance '
        "OpenCloud</em> ?"
    ),
    "index.lede": (
        "Saisissez l'adresse d'une instance dont vous avez la responsabilité. "
        "Ce serveur la contacte en HTTPS comme le ferait n'importe quel "
        "visiteur, lit ce qu'elle publie sans se connecter, et note le "
        "résultat de <strong>A+</strong> à <strong>F</strong>."
    ),
    "index.form.kicker": "Demande d'analyse",
    "index.form.hint": "Quelques secondes &middot; sans inscription",
    "index.error.self_host": (
        "Rien de personnel - ces limites sont ce qui permet à ce petit service "
        "de tenir debout. Le scanner est open source, vous pouvez donc "
        "exécuter exactement ce contrôle vous-même, aussi souvent que vous le "
        "souhaitez :"
    ),
    "index.field.label": "Adresse de l'instance",
    "index.field.title": (
        "L'adresse de base de l'instance : un nom d'hôte, un port facultatif "
        "et un sous-dossier simple facultatif. Aucune requête, aucun "
        "fragment, aucun paramètre, aucun caractère d'échappement ni "
        "traversée de chemin."
    ),
    "index.field.hint": (
        "Le nom d'hôte seul suffit - <code>https://</code> est supposé. Un "
        "sous-dossier tel que <code>/opencloud</code> est pris en charge ; les "
        "requêtes, fragments, paramètres et traversées de chemin sont "
        "refusés. Adresses publiques uniquement, et seulement des instances "
        "que vous exploitez ou que vous avez l'autorisation de tester."
    ),
    "index.field.invalid": (
        "Adresse non valide : un nom d'hôte, un port facultatif et un "
        "sous-dossier simple - aucune requête, fragment ni paramètre."
    ),
    "index.submit": "Démarrer l'audit",
    "index.submit.busy": "Démarrage de l'audit...",
    "index.track.label": "Canal de version",
    "index.track.hint": (
        "Détermine la durée de prise en charge de cette version et vers "
        "quelle version elle est invitée à évoluer."
    ),
    "index.format.label": "Afficher",
    "index.format.dashboard": "Un tableau de bord",
    "index.format.json": "Le JSON brut",
    "index.format.hint": "Les deux proviennent de la même analyse.",
    "index.waivers.summary": "Ignorer certains contrôles (facultatif)",
    "index.waivers.selected": "Ignorer certains contrôles ({count} sélectionné(s))",
    "index.waivers.hint": (
        "Un contrôle dérogé reste dans le rapport et continue d'être affiché - "
        "il cesse simplement de plomber la note. Seuls les contrôles "
        "réellement en échec peuvent faire l'objet d'une dérogation."
    ),
    "index.waivers.search.label": "Filtrer les contrôles",
    "index.waivers.search.placeholder": "Rechercher par nom...",
    "index.waivers.search.empty": "Aucun contrôle ne correspond à votre recherche.",
    "index.assurance.aria": "Comment ce service traite vos données",
    "index.assurance.airgapped.title": "100 % isolé",
    "index.assurance.airgapped.body": (
        "Chaque octet provient de cette origine. Aucun CDN, aucun service de "
        "polices, aucune analyse d'audience."
    ),
    "index.assurance.nostore.title": "Aucune donnée conservée",
    "index.assurance.nostore.body": (
        "Le résultat vit en mémoire et est supprimé dès qu'il expire."
    ),
    "index.assurance.noaccount.title": "Aucune inscription requise",
    "index.assurance.noaccount.body": (
        "Aucun compte, aucune inscription, aucune adresse e-mail, aucune "
        "attente."
    ),
    "index.assurance.ephemeral.title": "Résultats éphémères",
    "index.assurance.ephemeral.body": (
        "Le lien cesse de fonctionner {minutes} minutes après l'analyse."
    ),
    # -------------------------------------------- release tracks and waivers
    "track.auto.label": "Détecter automatiquement",
    "track.auto.description": (
        "Déduit le canal à partir de la version que l'instance annonce."
    ),
    "track.rolling.label": "Rolling",
    "track.rolling.description": "Une nouvelle version environ toutes les trois semaines.",
    "track.production.label": "Production",
    "track.production.description": (
        "Prise en charge pendant environ six mois. Le choix habituel."
    ),
    "track.lts.label": "LTS",
    "track.lts.description": "Prise en charge pendant deux ans.",
    "waivers.group.hardening": "Durcissement",
    "waivers.group.headers": "En-têtes",
    "waivers.group.checks": "Contrôles",
    # ------------------------------------------------------------ severity
    "severity.critical": "critique",
    "severity.high": "élevée",
    "severity.medium": "moyenne",
    "severity.low": "faible",
    # ------------------------------------------------------------ category
    "category.transport": "Transport & TLS",
    "category.cookies": "Cookies",
    "category.headers": "En-têtes de sécurité",
    "category.authentication": "Authentification & comptes",
    "category.sharing": "Partage & liens",
    "category.exposure": "Exposition réseau",
    "category.embedding": "Intégration",
    "category.lifecycle": "Version & cycle de vie",
    "category.proxy": "Fournisseur d'identité & proxy",
    # --------------------------------------------------------- grade scale
    "grade.5.headline": "Rien à signaler",
    "grade.5.meaning": (
        "La version est à jour pour son canal, aucun avis de sécurité ne "
        "correspond à cette version, et tous les contrôles que l'analyse a pu "
        "exécuter ont réussi."
    ),
    "grade.5.improve": (
        "Maintenez ce niveau : surveillez la prochaine version sur votre "
        "canal, et relancez l'analyse après toute modification du proxy "
        "inverse ou de la connexion."
    ),
    "grade.4.headline": "Une mise à jour est disponible",
    "grade.4.meaning": (
        "Une version corrective plus récente existe sur la même ligne de "
        "version. Rien n'indique un problème avec la version installée - elle "
        "n'est simplement pas la plus récente."
    ),
    "grade.4.improve": (
        "Installez la mise à jour en attente. Il s'agit de la même ligne de "
        "version, c'est donc la mise à niveau la plus légère possible."
    ),
    "grade.3.headline": "Une ligne de version de retard",
    "grade.3.meaning": (
        "L'instance utilise une ligne plus ancienne que celle actuelle pour "
        "son canal. Elle peut encore être prise en charge, mais ce n'est plus "
        "là que les correctifs arrivent en premier."
    ),
    "grade.3.improve": (
        "Passez à la ligne actuelle de votre canal. L'analyse indique "
        "laquelle, et ne vous oriente jamais vers un canal que vous n'avez pas "
        "choisi."
    ),
    "grade.2.headline": "Des avis de sécurité correspondent à cette version",
    "grade.2.meaning": (
        "La version installée figure dans la base de données des avis de "
        "sécurité. Aucun des avis correspondants n'est classé critique ou "
        "élevé, ce qui est la seule raison pour laquelle la note n'est pas "
        "plus basse."
    ),
    "grade.2.improve": (
        "Passez à la version corrigée pour votre ligne de version. La page de "
        "résultat l'indique - un même avis peut être corrigé séparément sur "
        "plusieurs lignes."
    ),
    "grade.1.headline": "Un avis critique ou élevé correspond",
    "grade.1.meaning": (
        "Au moins un avis correspondant à la version installée est classé "
        "critique ou élevé. Il s'agit d'une voie d'intrusion connue, publiée "
        "et corrigée."
    ),
    "grade.1.improve": (
        "Effectuez la mise à niveau maintenant, avant toute autre chose sur "
        "cette page. Aucun autre changement possible ne fera remonter la note "
        "au-delà de ce niveau."
    ),
    "grade.0.headline": "Hors support",
    "grade.0.meaning": (
        "La ligne de version ne reçoit plus aucun correctif de sécurité. Cela "
        "prime sur tout autre signal, y compris une dérogation : une instance "
        "que personne ne corrige ne peut pas être notée sur la propreté de ses "
        "en-têtes."
    ),
    "grade.0.improve": (
        "Passez à une ligne de version prise en charge. Les lignes prises en "
        "charge, et pour combien de temps, figurent dans le calendrier de "
        "versions que l'analyse consulte."
    ),
    # ---------------------------------------------------------- grades page
    "grades.title": "Ce que signifient les notes",
    "grades.description": (
        "A+, A, C, D, E et F : ce que dit chaque note d'une instance "
        "OpenCloud, ce qui la plombe, et le chemin le plus court vers la note "
        "supérieure."
    ),
    "grades.kicker": "L'échelle",
    "grades.lede": (
        "Chaque analyse se termine par une seule lettre. Elle est calculée à "
        "partir de deux éléments - la version exécutée par l'instance et les "
        "contrôles ayant échoué - et cette page présente l'intégralité de ce "
        "calcul, dans l'ordre où le scanner l'effectue."
    ),
    "grades.scale.kicker": "Six niveaux",
    "grades.scale.heading": "L'échelle, du meilleur au pire",
    "grades.scale.intro": (
        "L'échelle <strong>0-5</strong> et ses lettres sont celles que "
        "<code>scan.nextcloud.com</code> a rendues familières, conservées "
        "délibérément pour qu'un seuil, un graphique ou une règle d'alerte "
        "existants gardent leur sens. C'est aussi pourquoi il n'y a pas de "
        "<strong>B</strong> : l'échelle le saute, et en inventer un ici ferait "
        "correspondre deux nombres à la même note."
    ),
    "grades.row.prefix": "Note {label} : ",
    "grades.row.score": "{rating} sur 5",
    "grades.row.improve": "Pour progresser :",
    "grades.caps.kicker": "Le plafond",
    "grades.caps.heading": "Ce qu'un contrôle en échec peut faire à une note",
    "grades.caps.intro": (
        "La version définit la note de départ. Les contrôles en échec ne "
        "peuvent pas la faire remonter - ils peuvent seulement la plomber, et "
        "jusqu'où dépend de la gravité du pire contrôle en échec :"
    ),
    "grades.caps.at_best": "au mieux",
    "grades.caps.shared": (
        "Les constats de même gravité partagent un même plafond, si bien que "
        "corriger un constat moyen sur trois ne change rien tant que le "
        "dernier n'a pas disparu. C'est pourquoi la page de résultat ordonne "
        "le plan comme elle le fait, et pourquoi elle affiche la note que "
        "chaque étape permettrait réellement d'atteindre."
    ),
    "grades.caps.rules": (
        "Deux règles priment sur tout cela. <strong>La fin de vie prime sur "
        "tout</strong>, y compris une dérogation : une ligne de version qui ne "
        "reçoit plus de correctifs de sécurité obtient un <strong>F</strong>, "
        "aussi propre que soit le reste du rapport. Et <strong>être en avance "
        "sur son canal n'est pas être en retard</strong> - une version plus "
        "récente que la version actuelle du canal déclaré est signalée comme "
        "étant en avance et n'est jamais notée comme non prise en charge."
    ),
    "grades.improve.kicker": "Le chemin le plus court",
    "grades.improve.heading": "Comment ce scanner vous aide à progresser",
    "grades.improve.intro": (
        "Une note seule n'est qu'un tableau de score, ce qui n'est pas très "
        "utile à quatre heures de l'après-midi. Chaque page de résultat porte "
        "aussi les quatre éléments qui la transforment en travail concret "
        "pour l'après-midi :"
    ),
    "grades.improve.plan": (
        "<strong>Un plan de remédiation, dans l'ordre de rentabilité.</strong> "
        "Chaque étape indique ce qu'il faut changer et quelle note l'instance "
        "obtiendrait une fois cette étape et toutes celles qui la précèdent "
        "réalisées - vous pouvez ainsi vous arrêter là où le bénéfice "
        "s'arrête."
    ),
    "grades.improve.release": (
        "<strong>La version exacte vers laquelle évoluer.</strong> Pas "
        '« mettez à jour » : la version qui corrige l\'avis <em>sur la ligne '
        "où vous vous trouvez réellement</em>, et jamais un saut vers un canal "
        "que vous n'avez pas choisi."
    ),
    "grades.improve.explained": (
        "<strong>Chaque contrôle en échec, expliqué.</strong> Ce qui a été "
        "mesuré, pourquoi cela compte et le correctif, avec un lien vers la "
        "documentation OpenCloud du paramètre concerné."
    ),
    "grades.improve.waiver": (
        "<strong>Une dérogation pour ceux que vous avez décidé "
        "d'accepter.</strong> Un contrôle dérogé reste dans le rapport et "
        "reste visible - il cesse simplement de plafonner la note, si bien "
        "qu'une décision réfléchie ne se lit pas comme un échec pour "
        "toujours. Elle ne peut pas masquer un contrôle qui réussit, et elle "
        "ne peut pas sauver une version en fin de vie."
    ),
    "grades.improve.rerun": (
        "Relancez-la ensuite. La même instance, la même analyse, et la lettre "
        "bouge - c'est la seule preuve que tout cela a fonctionné."
    ),
    "grades.limits.kicker": "Honnêteté",
    "grades.limits.heading": "Ce qu'une bonne note n'est pas",
    "grades.limits.body": (
        "Un <strong>A+</strong> signifie que rien de ce que cette analyse a "
        "examiné n'a posé problème. Ce n'est pas un certificat, et ce n'est "
        "pas un test d'intrusion. Tout ce qui se trouve derrière la "
        "connexion, le système d'exploitation, l'environnement d'exécution "
        "des conteneurs, les sauvegardes, les comptes et les personnes qui "
        "les détiennent sont hors de portée de ce qu'une analyse non "
        "authentifiée peut voir. Considérez la lettre comme un élément parmi "
        'd\'autres - <a href="/how-it-works">le fonctionnement de '
        "l'analyse</a> énumère ce qu'elle lit, et chaque page de résultat "
        "rappelle les limites sous la note."
    ),
    # -------------------------------------------------------------- catalogue
    "catalogue.title": "Ce que le scanner vérifie",
    "catalogue.description": (
        "Chaque indicateur de durcissement, en-tête de sécurité, vérification "
        "TLS et vulnérabilité connue que ce scanner peut signaler, "
        "indépendamment d'un résultat d'analyse particulier."
    ),
    "catalogue.kicker": "Référence",
    "catalogue.lede": (
        "Voici l'ensemble complet : chaque contrôle ci-dessous peut "
        "apparaître sur une page de résultat, et chaque vulnérabilité "
        "ci-dessous est une de celles contre lesquelles une analyse est "
        "évaluée. Rien ici ne dépend d'une instance particulière."
    ),
    "catalogue.checks.kicker": "Contrôles",
    "catalogue.checks.heading": "Chaque contrôle, par catégorie",
    "catalogue.checks.lede": (
        "Regroupés par sujet plutôt que par gravité - la gravité dépend de "
        "l'instance analysée, elle n'est donc pas indiquée ici."
    ),
    "catalogue.checks.not_configurable": "non configurable",
    "catalogue.advisories.kicker": "Vulnérabilités",
    "catalogue.advisories.heading": "Vulnérabilités connues",
    "catalogue.advisories.lede": (
        "Chaque vulnérabilité de la base contre laquelle une analyse est "
        "évaluée, actualisée chaque jour depuis le flux public."
    ),
    "catalogue.advisories.empty.tag": "Aucune connue",
    "catalogue.advisories.empty.body": (
        "La base de données de vulnérabilités est actuellement vide."
    ),
    "catalogue.advisories.fixed_in": "Corrigé dans {version}",
    "catalogue.advisories.unfixed": "Aucun correctif publié pour le moment",
    # -------------------------------------------------- how the scan works
    "how.title": "Comment fonctionne l'analyse",
    "how.description": (
        "Ce que ce scanner teste sur une instance OpenCloud, et ce qui se "
        "passe entre le clic sur le bouton et la lecture de la note."
    ),
    "how.kicker": "La méthode",
    "how.lede": (
        "Tout ce que ce service rapporte, il le détermine lui-même, en "
        "contactant l'adresse que vous saisissez en HTTPS comme le ferait "
        "n'importe quel visiteur. Rien n'est demandé à un tiers, et aucune "
        "connexion n'est effectuée."
    ),
    "how.tests.heading": "Ce qui est testé",
    "how.tests.version.title": "Version et cycle de vie",
    "how.tests.version.body": (
        "Quelle version est exécutée, si elle reçoit encore des correctifs de "
        "sécurité, et si un avis publié la concerne. Une version passée en "
        "fin de vie obtient un F, quoi que soit le reste."
    ),
    "how.tests.transport.title": "Transport et en-têtes",
    "how.tests.transport.body": (
        "Accessibilité en HTTPS, le certificat et sa durée de validité "
        "restante, les versions TLS proposées, et les en-têtes de sécurité "
        "réellement envoyés à un navigateur - HSTS, CSP, protection contre le "
        "cadrage et le type de contenu."
    ),
    "how.tests.hardening.title": "Durcissement et exposition",
    "how.tests.hardening.body": (
        "Authentification de base, politique de mot de passe et d'expiration "
        "des liens publics, règles de mot de passe, listage de répertoires, "
        "points de terminaison exposés et tout ce qui annonce la version au "
        "monde entier."
    ),
    "how.pipeline.kicker": "Le déroulement",
    "how.pipeline.heading": "Ce qui se passe quand vous cliquez sur le bouton",
    "how.pipeline.lede": (
        "Quatre étapes, et c'est à la troisième que la file d'attente "
        "intervient."
    ),
    "how.pipeline.step1": (
        "<strong>Votre adresse est vérifiée.</strong> Les adresses privées, de "
        "bouclage et de métadonnées cloud sont refusées avant toute "
        "connexion."
    ),
    "how.pipeline.step2": (
        "<strong>Une analyse reçoit un identifiant aléatoire.</strong> Cet "
        "identifiant est le seul moyen d'accéder au résultat. Il n'existe "
        "aucune liste d'analyses, ni aucun moyen d'en deviner un."
    ),
    "how.pipeline.step3": (
        "<strong>Elle attend son tour.</strong> Un nombre fixe d'analyses "
        "s'exécutent simultanément. Si elles sont toutes occupées, la vôtre "
        "patiente en file d'attente et l'on vous indique votre position - "
        "rien n'est rejeté parce que le service est populaire."
    ),
    "how.pipeline.step4": (
        "<strong>Le résultat expire.</strong> Après {minutes} minutes, "
        "l'identifiant cesse de fonctionner et le résultat disparaît, sans "
        "rien écrit sur le disque."
    ),
    "how.faq.kicker": "Questions",
    "how.faq.heading": "Questions fréquentes",
    "how.faq.q1": "S'agit-il du logiciel officiel d'OpenCloud ?",
    "how.faq.a1": (
        "Non. Il s'agit d'un projet communautaire indépendant, qui n'est pas "
        "affilié à OpenCloud GmbH et que cette société ne recommande ni ne "
        'prend en charge. "OpenCloud" et son logo sont des marques '
        "appartenant à leurs détenteurs respectifs, utilisées ici uniquement "
        "pour indiquer quel logiciel cet outil contrôle."
    ),
    "how.faq.q2": "Une bonne note signifie-t-elle qu'une instance est sécurisée ?",
    "how.faq.a2": (
        "Non. L'analyse lit uniquement ce qu'une instance accessible "
        "publiquement montre à un visiteur anonyme : sa version, les avis de "
        "sécurité concernant cette version, son transport, ses en-têtes et un "
        "ensemble de réglages visibles sans connexion. Tout ce qui se trouve "
        "derrière la connexion, le serveur sur lequel elle tourne, le réseau "
        "qui l'entoure et les personnes disposant d'un compte en sont exclus - "
        "une analyse non authentifiée ne peut pas les voir. Considérez un "
        "résultat comme un élément parmi d'autres, jamais comme un audit de "
        "sécurité ou un test d'intrusion."
    ),
    "how.faq.q3": "Combien de temps conservez-vous le résultat d'une analyse ?",
    "how.faq.a3": (
        "Uniquement en mémoire, pendant {minutes} minutes, puis il disparaît. "
        "Aucun compte, aucune analyse statistique, aucun traceur - le reste se "
        '<a href="/privacy">trouve sur ce que ce serveur conserve</a>.'
    ),
    "how.faq.q4": "Y a-t-il une limite de débit ?",
    "how.faq.a4": (
        "Oui, par visiteur et par cible analysée, afin qu'un visiteur trop "
        "actif n'accapare pas la file d'attente et que la même instance ne "
        "soit pas analysée coup sur coup. Les chiffres exacts de ce "
        'déploiement figurent sur la <a href="/api#api-limits">page de '
        "l'API</a>."
    ),
    "how.faq.q5": "Puis-je analyser sans limite de débit ?",
    "how.faq.a5": (
        "Oui - le scanner est open source. Exécutez-le vous-même avec "
        '<a href="/cli">une seule commande Docker</a> sur votre propre '
        "machine, sans limite et sans site web intermédiaire."
    ),
    "how.faq.q6": "Un scan m'indique-t-il si une mise à jour d'OpenCloud est en attente ?",
    "how.faq.a6": (
        "Oui. Chaque scan compare la version signalée au flux des versions "
        "d'OpenCloud et signale une mise à jour en attente ou une version qui "
        "n'est plus prise en charge, de la même façon qu'il signale un "
        'en-tête manquant - voir <a href="/documentation/reference#update-check">'
        "la vérification des mises à jour</a> pour savoir comment la version "
        "recommandée est déterminée."
    ),
    # --------------------------------------------------------------- privacy
    "privacy.title": "Ce que ce serveur conserve",
    "privacy.description": (
        "Ce qui est stocké pendant l'exécution d'une analyse, pour combien de "
        "temps, et ce que le journal opérationnel enregistre ou non."
    ),
    "privacy.kicker": "Confidentialité",
    "privacy.lede": "En bref : l'analyse, pendant {minutes} minutes, en mémoire.",
    "privacy.retention.kicker": "Rétention",
    "privacy.retention.heading": "Pendant qu'une analyse est active",
    "privacy.retention.body": (
        "L'adresse que vous soumettez, les contrôles que vous avez choisi de "
        "déroger et le résultat vivent en mémoire pendant {minutes} minutes, "
        "sous une clé dérivée de l'identifiant aléatoire de votre analyse, "
        "puis sont supprimés par le magasin lui-même. Le journal opérationnel "
        "enregistre qu'une analyse a été créée, démarrée et terminée, "
        "identifiée uniquement par cet identifiant aléatoire - ni l'adresse, "
        "ni le résultat, ni votre adresse IP, qui n'est jamais comptée que "
        "comme une empreinte à sens unique pour la limitation de débit."
    ),
    "privacy.self_host": (
        "Vous préférez l'exécuter vous-même ? Le même scanner existe sous "
        "forme de contrôle en ligne de commande et de paquet Python. Dans les "
        "deux cas, rien ici ne communique avec un service tiers."
    ),
    # ----------------------------------------------------------- legal notice
    "legal.title": "Mentions légales",
    "legal.description": (
        "Identification du fournisseur, coordonnées et clauses de "
        "responsabilité de l'exploitant de cette installation."
    ),
    "legal.kicker": "Mentions légales",
    "legal.lede": (
        "Identification du fournisseur selon le droit allemand, pour "
        "l'exploitant de cette installation."
    ),
    "legal.english_notice": (
        "Ces mentions sont le texte juridique de l'exploitant et ne sont "
        "disponibles qu'en anglais. La page qui les entoure est traduite, le "
        "texte ci-dessous ne l'est pas."
    ),
    # ----------------------------------------------------------------- about
    "about.title": "À propos d'OpenCloud et de ce scanner",
    "about.description": (
        "Ce qu'est OpenCloud, qui le développe, et pourquoi ce scanner est un "
        "projet communautaire indépendant."
    ),
    "about.kicker": "À propos",
    "about.lede": (
        "L'un est une plateforme de fichiers, de synchronisation et de "
        "partage. L'autre est un contrôle communautaire qui l'observe de "
        "l'extérieur."
    ),
    "about.platform.kicker": "La plateforme",
    "about.platform.heading": "À propos d'OpenCloud",
    "about.platform.body": (
        '<a href="https://opencloud.eu/" rel="noopener noreferrer">OpenCloud'
        "</a> est la plateforme de fichiers, de synchronisation et de partage "
        "que cet outil contrôle - open source, développée en Allemagne, et "
        'documentée sur <a href="https://docs.opencloud.eu/" '
        'rel="noopener noreferrer">docs.opencloud.eu</a>, où chaque correctif '
        "que ce scanner suggère est correctement documenté. Merci aux "
        "personnes qui la font vivre."
    ),
    "about.platform.independent": (
        "Ce scanner est un projet communautaire indépendant. Il n'est pas "
        "affilié à OpenCloud GmbH et n'est ni recommandé ni pris en charge "
        "par cette société. &ldquo;OpenCloud&rdquo;, le logo OpenCloud et "
        "toutes les marques associées sont la propriété de leurs détenteurs "
        "respectifs."
    ),
    "about.project.kicker": "Le projet",
    "about.project.heading": "À propos de ce scanner",
    "about.project.body": (
        "Tout ce que vous voyez ici est produit par "
        "<code>check-opencloud-security</code>, un plugin Nagios et Icinga "
        "adossé à une bibliothèque de scan. Cette page est une façon de "
        "l'utiliser ; une commande sur votre propre machine, sans limite de "
        "débit ni file d'attente, en est une autre."
    ),
    "about.project.origin": (
        "Le projet a été créé par <strong>Massoud Ahmed</strong> pour offrir "
        "aux utilisateurs d'OpenCloud une alternative indépendante à "
        "<code>scan.nextcloud.com</code> : un scanner conçu pour les canaux de "
        "version, les paramètres et le modèle de déploiement d'OpenCloud, qui "
        "peut s'exécuter entièrement sur la propre machine de l'exploitant. "
        '<a href="{project}" rel="noopener noreferrer">Le projet est sur '
        "GitHub</a>."
    ),
    # ------------------------------------------------------------------- API
    "api.title": "Analyser depuis un script",
    "api.description": (
        "L'API JSON derrière le formulaire : comment soumettre une analyse, "
        "l'interroger, et ce que ce serveur refuse de laisser décider à "
        "l'appelant."
    ),
    "api.kicker": "L'API",
    "api.lede": (
        "Le formulaire est l'une des deux portes d'entrée ; l'autre est le "
        "JSON, et c'est le même gestionnaire."
    ),
    "api.submit.kicker": "Soumettre et interroger",
    "api.submit.heading": "Soumettre et interroger",
    "api.submit.body": (
        "Une soumission répond <code>202</code> avec l'identifiant de "
        "l'analyse ; l'interroger renvoie <code>queued</code>, "
        "<code>running</code> ou le résultat terminé, et <code>404</code> une "
        "fois qu'il a expiré. Seuls quatre champs sont lus - l'adresse, les "
        "contrôles à déroger, le canal de version et le format de sortie. "
        "Tout le reste dans le corps, la concurrence et les délais "
        "d'expiration en premier lieu, est rejeté : l'intensité avec laquelle "
        "ce serveur sonde n'est pas une décision de l'appelant."
    ),
    "api.limits.kicker": "Utilisation raisonnable",
    "api.limits.heading": "Utilisation raisonnable",
    "api.limits.enforced": (
        "L'utilisation raisonnable est imposée plutôt que demandée : {client} "
        "soumissions par {window} minute(s) depuis une même adresse, et "
        "{cooldown}, toutes deux sanctionnées par un <code>429</code> et un "
        "<code>Retry-After</code>."
    ),
    "api.limits.cooldown": "une analyse par cible toutes les {minutes} minute(s)",
    "api.limits.no_cooldown": "aucun délai de repos par cible",
    "api.limits.none": "Ce déploiement n'impose aucune limite de débit.",
    "api.limits.self_host": (
        "Si vous en rencontrez une et préférez ne pas attendre, l'ensemble "
        'tourne aussi sur votre propre machine : <a href="{project}" '
        'rel="noopener noreferrer">le projet est sur GitHub</a>.'
    ),
    "api.schema.kicker": "Le schéma",
    "api.schema.heading": "Le schéma",
    "api.schema.body": (
        "Les documents lisibles par machine sont toujours publics, sur ce "
        'déploiement comme sur tout autre : la <a href="/openapi.json">'
        "description OpenAPI 3.1</a> de chaque opération, et les "
        '<a href="/arazzo.json">flux de travail Arazzo 1.0.1</a> qui '
        "expliquent comment ces opérations s'assemblent pour soumettre une "
        "analyse, l'attendre et en récupérer le résultat."
    ),
    "api.schema.docs_on": (
        'Les deux sont consultables ici sous forme de <a href="/docs">'
        'Swagger UI</a> et de <a href="/redoc">ReDoc</a>, servis depuis ce '
        "serveur comme tout le reste - rien n'est récupéré ailleurs."
    ),
    "api.schema.docs_off": (
        "Les visionneuses interactives (Swagger UI sur <code>/docs</code>, "
        "ReDoc sur <code>/redoc</code>) sont désactivées sur ce déploiement ; "
        "un opérateur les active avec <code>COS_WEB_ENABLE_DOCS=true</code>."
    ),
    "api.agents.kicker": "Agents",
    "api.agents.heading": "Pour les agents IA",
    "api.agents.body": (
        "Les logiciels qui n'ont pas été conçus pour ce service disposent de "
        'leur propre page : <a href="/ai">pour les agents IA</a> rassemble en '
        "un seul endroit le document de découverte, le schéma OpenAPI, les "
        "flux de travail Arazzo et le point de terminaison MCP."
    ),
    # -------------------------------------------------------------------- AI
    "ai.title": "Pour les agents IA",
    "ai.description": (
        "Tout ce dont un logiciel a besoin pour utiliser ce scanner sans "
        "avoir été conçu pour lui : le document de découverte, le schéma "
        "OpenAPI, les flux de travail Arazzo et le point de terminaison MCP."
    ),
    "ai.kicker": "Invités machines",
    "ai.lede": (
        "Ce service est conçu pour être utilisable par des logiciels qui "
        "n'ont pas été écrits pour lui. Tout ce dont un agent a besoin est "
        "publié, ouvertement, sans compte : ce que l'API peut faire, comment "
        "ses appels s'assemblent en une tâche, et un moyen d'exécuter "
        "directement cette tâche."
    ),
    "ai.discovery.kicker": "Découverte",
    "ai.discovery.heading": "Partez d'une seule adresse",
    "ai.discovery.discovery": (
        '<strong>Découverte</strong> - <a href="/.well-known/ai.json">'
        "/.well-known/ai.json</a> nomme tout ce qui suit, avec des URL "
        "absolues. Commencez ici."
    ),
    "ai.discovery.openapi": (
        '<strong>OpenAPI</strong> - <a href="/openapi.json">/openapi.json</a>, '
        "chaque opération avec ses véritables codes de statut et formes de "
        "réponse."
    ),
    "ai.discovery.arazzo": (
        '<strong>Flux de travail Arazzo</strong> - <a href="/arazzo.json">'
        "/arazzo.json</a>, le cycle de vie d'une analyse : soumettre, "
        "interroger, détecter l'achèvement, exporter."
    ),
    "ai.discovery.mcp": (
        "<strong>MCP</strong> - <code>{url}</code>, un point de terminaison "
        "Model Context Protocol via HTTP en flux continu. Outils : "
        "<code>scan_instance</code>, <code>scan_instances</code>, "
        "<code>get_scan_result</code>, <code>plan_remediation</code>, "
        "<code>export_scan</code> et <code>erase_instance_data</code>. "
        "<code>scan_instance</code> effectue toute la tâche - soumission, "
        "attente et résultat - en un seul appel. Les invites (prompts) "
        "nomment les tâches elles-mêmes, comme <code>audit_instance</code>, "
        "qui audite une instance et rédige le plan de remédiation, et "
        "<code>review_transport_security</code>, qui ne s'intéresse qu'au "
        "certificat et à la négociation. Il répond au protocole plutôt qu'à "
        "un navigateur, c'est donc une adresse à configurer plutôt qu'une "
        "page à ouvrir."
    ),
    "ai.discovery.summary": (
        "Les trois documents décrivent un même service sous trois angles : "
        "OpenAPI dit ce que l'API peut faire, et Arazzo dit comment ces "
        "opérations s'assemblent en une tâche. Ils sont générés à partir du "
        "même code que celui exécuté par le serveur, si bien qu'aucun d'eux "
        "ne peut discrètement devenir obsolète."
    ),
    "ai.discovery.summary_mcp": (
        "Les trois documents décrivent un même service sous trois angles : "
        "OpenAPI dit ce que l'API peut faire, Arazzo dit comment ces "
        "opérations s'assemblent en une tâche, et MCP confie cette tâche à un "
        "agent sous la forme d'un outil qu'il peut appeler. Ils sont générés "
        "à partir du même code que celui exécuté par le serveur, si bien "
        "qu'aucun d'eux ne peut discrètement devenir obsolète."
    ),
    "ai.webmcp.kicker": "Dans le navigateur",
    "ai.webmcp.heading": "Utiliser la page comme outil",
    "ai.webmcp.intro": (
        "Un navigateur compatible avec le "
        '<a href="https://webmachinelearning.github.io/webmcp/" '
        'rel="noopener noreferrer">projet WebMCP</a> peut découvrir les actions '
        "de la page ouverte. Aucun autre client ne doit être configuré."
    ),
    "ai.webmcp.landing": (
        "Sur la page d'accueil, <code>scan_opencloud_security</code> met une "
        "analyse en file d'attente. Son schéma contient les canaux de publication, "
        "les formats de sortie et les dérogations proposés par cette page."
    ),
    "ai.webmcp.result": (
        "Sur une page de résultat, <code>get_scan_result</code> lit l'analyse "
        "actuelle et <code>export_scan_report</code> télécharge JSON, CSV, SARIF "
        "ou PDF pour l'uuid déjà affiché."
    ),
    "ai.webmcp.boundary": (
        "Chaque outil du navigateur appelle la même API JSON avec "
        "<code>Accept: application/json</code>. La protection SSRF, les limites, "
        "le délai par cible, la file et l'isolation par uuid restent appliqués."
    ),
    "ai.webmcp.support": (
        "WebMCP est encore un projet et les navigateurs qui ne l'implémentent pas "
        "l'ignorent. Désactiver MCP pour ce déploiement retire aussi les outils du "
        "navigateur."
    ),
    "ai.clients.kicker": "Configuration",
    "ai.clients.heading": "Le connecter à un client",
    "ai.clients.intro": (
        "La plupart des outils d'agents attendent une URL et un transport. "
        "Celui-ci est en HTTP en flux continu, sans authentification et sans "
        "compte :"
    ),
    "ai.clients.body": (
        "Une configuration détaillée pour Claude Code, Claude Desktop, "
        "GitHub Copilot dans VS Code et en CLI, Cursor, Zed et Windsurf - "
        "contre ce déploiement ou l'un des vôtres - se trouve dans "
        '<a href="{project}/blob/main/docs/mcp.md" '
        'rel="noopener noreferrer">le guide MCP</a>.'
    ),
    "ai.rules.kicker": "Les règles",
    "ai.rules.heading": "Les mêmes règles que pour tout le monde",
    "ai.rules.body": (
        "Les règles sont les mêmes pour un agent que pour n'importe qui "
        "d'autre. Une analyse est asynchrone et l'uuid est le seul moyen d'y "
        "revenir ; un <code>429</code> est une invitation à ralentir plutôt "
        "qu'un refus ; et si vous contrôlez plus qu'une poignée d'instances, "
        'merci d\'<a href="{project}" rel="noopener noreferrer">exécuter le '
        "scanner vous-même</a> - c'est le même code, sur votre machine, sans "
        "aucune limite."
    ),
    # -------------------------------- Docker one-liners, on /documentation
    "cli.lede": (
        "Confier une adresse au serveur d'un inconnu est une hésitation "
        "raisonnable. Vous n'y êtes pas obligé : cette page est le même "
        "contrôle, sous forme d'une seule commande sur votre propre machine."
    ),
    "cli.oneliner.kicker": "La commande unique",
    "cli.oneliner.heading": "Une commande, rien à installer",
    "cli.oneliner.body": (
        "C'est tout. Elle affiche le même verdict que celui que ce site "
        "établit - la note, le cycle de vie de la version, les avis de "
        "sécurité et chaque contrôle en échec - et se termine avec le code de "
        "statut Nagios, si bien que la même ligne fonctionne dans un script, "
        "un pipeline ou une tâche cron. Rien n'est envoyé nulle part : le "
        "conteneur ne parle qu'à votre instance et à personne d'autre."
    ),
    "cli.json.kicker": "En JSON",
    "cli.json.heading": "L'intégralité du document de résultat",
    "cli.json.body": (
        "Chaque chiffre d'une page de résultat provient de ce document, y "
        "compris le bloc <code>addresses</code> derrière la ligne "
        "<strong>Résolu vers</strong> - les adresses IPv4 et IPv6 vers "
        "lesquelles le nom pointait pendant l'analyse."
    ),
    "cli.private.kicker": "Votre propre réseau",
    "cli.private.heading": "Les instances que ce site n'analysera pas",
    "cli.private.body": (
        "Un service public qui analyserait des adresses privées est un "
        "service public que l'on pourrait diriger vers le réseau interne de "
        "quelqu'un d'autre, c'est pourquoi celui-ci refuse. Votre propre "
        "machine n'a pas ce problème : un serveur de préproduction, un nom "
        "que seul votre résolveur connaît ou une instance qui ne quitte "
        "jamais le réseau local fonctionnent tous depuis la ligne de "
        "commande."
    ),
    "cli.nodocker.kicker": "Pas de Docker ?",
    "cli.nodocker.heading": "Sans conteneur",
    "cli.nodocker.body": (
        "Le contrôle est un simple programme Python sur PyPI, si bien "
        "qu'<code>uv</code> ou <code>pipx</code> le récupèrent et l'exécutent "
        "sans rien installer de façon permanente."
    ),
    # ------------------------------------------------ CLI documentation index
    "docs.index.title": "Documentation en ligne de commande",
    "docs.index.description": (
        "Installez, exécutez et configurez le CLI check-opencloud-security, "
        "avec les guides complets destinés aux opérateurs rassemblés en un "
        "seul endroit."
    ),
    "docs.index.kicker": "Documentation",
    "docs.index.heading": "Exécutez le scanner depuis votre terminal",
    "docs.index.lede": (
        "La référence pratique de la ligne de commande, rassemblée à partir "
        "du README du projet et des guides sous <code>docs/</code>. Commencez "
        "par une seule commande ; gardez le reste pour quand le contrôle "
        "s'intègre à la supervision, à l'intégration continue ou à un parc "
        "de machines."
    ),
    "docs.index.toc.quickstart": "Démarrage rapide",
    "docs.index.toc.commands": "Commandes",
    "docs.index.toc.options": "Options utiles",
    "docs.index.toc.configuration": "Configuration",
    "docs.index.toc.monitoring": "Supervision",
    "docs.index.toc.guides": "Guides complets",
    "docs.index.quickstart.kicker": "Démarrage rapide",
    "docs.index.quickstart.heading": "Un contrôle, sans rien installer",
    "docs.index.quickstart.container": (
        "Ou utilisez le conteneur publié. Il exécute le même plugin et "
        "renvoie le même code de sortie Nagios/Icinga :"
    ),
    "docs.index.quickstart.note": (
        "Le plugin parle directement à l'instance. Il n'envoie pas l'adresse "
        "à ce site web ni à un service de verdict distant."
    ),
    "docs.index.commands.kicker": "Deux points d'entrée",
    "docs.index.commands.heading": "Le verdict et le document de résultat",
    "docs.index.commands.plugin": (
        "Le plugin de supervision : une ligne d'alerte, des données de "
        "performance et les codes de sortie standards <strong>OK</strong>, "
        "<strong>WARNING</strong>, <strong>CRITICAL</strong> et "
        "<strong>UNKNOWN</strong>."
    ),
    "docs.index.commands.scanner": (
        "La bibliothèque de scan en ligne de commande : le document de "
        "résultat JSON complet pour un script, un pipeline ou une "
        "investigation ponctuelle."
    ),
    "docs.index.options.kicker": "Les options du quotidien",
    "docs.index.options.heading": "Options utiles",
    "docs.index.option.host": (
        "Nom d'hôte, IP ou URL ; séparés par des virgules pour plusieurs "
        "instances."
    ),
    "docs.index.option.check_hardening": (
        "Inclure les mesures de durcissement manquantes et les en-têtes de "
        "sécurité."
    ),
    "docs.index.option.release_track": (
        "<code>rolling</code>, <code>production</code>, <code>lts</code> ou "
        "<code>auto</code>."
    ),
    "docs.index.option.ignore_hardening": (
        "Accepter un constat sans effacer sa preuve ; répétable et "
        "compatible avec les jokers."
    ),
    "docs.index.option.debug": (
        "Expliquer d'où part la note et ce qui l'a plombée."
    ),
    "docs.index.option.insecure": (
        "Ignorer la vérification du certificat pour une instance que vous "
        "contrôlez."
    ),
    "docs.index.option.thresholds": (
        "Choisir les seuils de notation correspondant aux états de "
        "supervision."
    ),
    "docs.index.option.format": "Afficher la sortie Nagios ou le texte Prometheus.",
    "docs.index.option.baseline": (
        "N'alerter que sur les constats nouveaux ou pires que lors de la "
        "dernière exécution."
    ),
    "docs.index.option.webhook": (
        "Notifier un autre système lorsque l'état configuré est atteint."
    ),
    "docs.index.options.manual": (
        "<code>check-opencloud-security --help</code> est le manuel "
        'installé. Le <a href="{project}#cli-usage" '
        'rel="noopener noreferrer">tableau complet des options</a> inclut '
        "chaque valeur par défaut et sa variable d'environnement "
        "<code>COS_</code>."
    ),
    "docs.index.configuration.kicker": "Un seul sens",
    "docs.index.configuration.heading": "Configuration et priorité",
    "docs.index.configuration.intro": (
        "Les paramètres peuvent provenir d'un fichier YAML ou JSON, de "
        "l'environnement ou de la ligne de commande. L'ordre est toujours :"
    ),
    "docs.index.precedence.aria": (
        "Priorité de configuration, du plus prioritaire au moins prioritaire"
    ),
    "docs.index.precedence.cli": "Option en ligne de commande",
    "docs.index.precedence.cli.note": "la réponse explicite pour cette exécution",
    "docs.index.precedence.env": "Environnement",
    "docs.index.precedence.env.note": (
        "<code>COS_*</code>, utile dans les conteneurs et les services"
    ),
    "docs.index.precedence.file": "Fichier de configuration",
    "docs.index.precedence.file.note": (
        "les valeurs par défaut durables de l'opérateur"
    ),
    "docs.index.precedence.default": "Valeur par défaut intégrée",
    "docs.index.precedence.default.note": (
        "la réponse sûre lorsque rien n'a été précisé"
    ),
    "docs.index.configuration.wizard": (
        "Laissez l'assistant rédiger le premier fichier :"
    ),
    "docs.index.configuration.note": (
        "Un fichier se terminant par <code>.json</code> est du JSON ; tout "
        "autre suffixe est du YAML. Les secrets peuvent vivre dans des "
        "fichiers séparés plutôt que sur la ligne de commande."
    ),
    "docs.index.monitoring.kicker": "Mettez-le au travail",
    "docs.index.monitoring.heading": (
        "Supervision, automatisation et plusieurs instances"
    ),
    "docs.index.monitoring.nagios": (
        "<strong>Nagios ou Icinga :</strong> utilisez directement la sortie "
        "du plugin ; le pire seuil configuré détermine le code de sortie."
    ),
    "docs.index.monitoring.fleet": (
        "<strong>Plusieurs instances :</strong> transmettez une liste "
        "d'hôtes séparés par des virgules, ou utilisez un fichier de "
        "configuration par instance dès que leurs paramètres divergent."
    ),
    "docs.index.monitoring.prometheus": (
        "<strong>Prometheus :</strong> utilisez "
        "<code>--format=prometheus</code> ponctuellement, ou exposez "
        "l'exportateur intégré avec <code>--prometheus-listen-port</code>."
    ),
    "docs.index.monitoring.ci": (
        "<strong>CI :</strong> exécutez la même commande dans un pipeline ; "
        "le code de statut fait échouer la tâche en cas de politique non "
        "respectée, sans script intermédiaire."
    ),
    "docs.index.monitoring.scheduled": (
        "<strong>Contrôles planifiés :</strong> systemd, cron, Kubernetes et "
        "le rôle Ansible utilisent tous le même flux de CLI et de "
        "configuration."
    ),
    "docs.index.guides.kicker": "Depuis le dépôt",
    "docs.index.guides.heading": "Guides complets pour les opérateurs",
    "docs.index.guides.lede": (
        "Chaque document source dispose ici de sa propre page HTML, générée "
        "à partir du Markdown du dépôt et vérifiée contre toute dérive en "
        "intégration continue."
    ),
    # --------------------------------------------------- generated guide pages
    "docs.guide.kicker": "Documentation en ligne de commande",
    "docs.guide.english_notice": (
        "Ce guide est généré à partir de la documentation du projet et n'est "
        "disponible qu'en anglais. La page qui l'entoure est traduite ; le "
        "texte ci-dessous ne l'est pas."
    ),
    "docs.guide.toc.heading": "Sur cette page",
    "docs.guide.toc.aria": "Sur cette page",
    # ----------------------------------------------------------------- search
    "search.title": "Recherche",
    "search.description": (
        "Recherchez dans la documentation du scanner et les recommandations "
        "publiques. Les résultats d'analyse ne sont jamais indexés."
    ),
    "search.eyebrow": "Index statique de la version",
    "search.heading": "Rechercher dans le scanner",
    "search.lede": (
        "Uniquement la documentation et les recommandations publiques. "
        "L'index est reconstruit à chaque version ; il ne lit jamais le "
        "magasin d'analyses, les pages de résultat, les UUID ou les adresses "
        "soumises."
    ),
    "search.label": "Rechercher dans la documentation",
    "search.placeholder": "TLS, Docker, dérogations...",
    "search.submit": "Rechercher",
    "search.status.idle": (
        "Saisissez un terme pour rechercher dans la documentation de cette "
        "version."
    ),
    "search.status.results": "{count} résultat(s) dans cette version.",
    "search.status.empty": (
        "Aucune documentation publique ne correspond à cette recherche."
    ),
    "search.status.error": "La recherche est temporairement indisponible.",
    # The search manifest: the title and summary an index entry carries, as
    # opposed to the words on the page itself.
    "search.page.index.title": "Analyser une instance OpenCloud",
    "search.page.index.summary": (
        "Lancez une analyse de sécurité publique sur une instance OpenCloud."
    ),
    "search.page.how.title": "Comment fonctionne le scanner",
    "search.page.how.summary": (
        "Ce que le scanner mesure, ce qu'il ne peut pas voir, et comment les "
        "résultats sont traités."
    ),
    "search.page.grades.title": "Ce que signifient les notes",
    "search.page.grades.summary": (
        "L'échelle de notation de A+ à F et les correctifs qui améliorent "
        "chaque note."
    ),
    "search.page.catalogue.title": "Ce que le scanner vérifie",
    "search.page.catalogue.summary": (
        "Chaque indicateur de durcissement, en-tête et vérification TLS du "
        "scanner, et chaque vulnérabilité connue."
    ),
    "search.page.documentation.title": "Documentation en ligne de commande",
    "search.page.documentation.summary": (
        "Démarrage rapide en ligne de commande, configuration, supervision "
        "et guides de déploiement."
    ),
    "search.page.api.title": "API",
    "search.page.api.summary": (
        "Soumettez des analyses, interrogez les résultats, exportez des "
        "rapports et effacez les données conservées."
    ),
    "search.page.ai.title": "IA et MCP",
    "search.page.ai.summary": (
        "OpenAPI, Arazzo, découverte, outils MCP et invites lisibles par "
        "machine."
    ),
    "search.page.privacy.title": "Confidentialité",
    "search.page.privacy.summary": (
        "Rétention des résultats, journalisation des requêtes, limites de "
        "débit et politique envers les tiers."
    ),
    "search.page.about.title": "À propos de ce projet",
    "search.page.about.summary": (
        "Pourquoi ce scanner de sécurité OpenCloud indépendant existe."
    ),
    # ------------------------------------------- what a submission is refused for
    # The API answers the English sentence these translate; a browser reads
    # the translation. The SSRF guard names the identifier, this names the
    # sentence, and neither is derived from the other.
    "error.unsupported_fields": (
        "Ce service n'accepte pas {fields}. L'analyse s'exécute uniquement "
        "avec les paramètres définis côté serveur."
    ),
    "error.rate_limit.client": (
        "C'est beaucoup d'analyses depuis votre réseau en peu de temps. "
        "Patientez une minute et réessayez."
    ),
    "error.rate_limit.target": (
        "Cette instance a été analysée très récemment. Merci de patienter "
        "quelques minutes."
    ),
    "error.target.invalid": "Cette adresse ne peut pas être analysée.",
    "error.target.empty": "Saisissez l'adresse de l'instance OpenCloud à analyser.",
    "error.target.too_long": "Cette adresse est trop longue.",
    "error.target.characters": (
        "Cette adresse contient des caractères qu'un nom d'hôte ne peut pas "
        "avoir."
    ),
    "error.target.unparsed": "Cette adresse n'a pas pu être analysée syntaxiquement.",
    "error.target.scheme": (
        "Seules les cibles en http:// et https:// peuvent être analysées."
    ),
    "error.target.credentials": (
        "Les identifiants inclus dans l'adresse ne sont pas acceptés."
    ),
    "error.target.address_only": (
        "Saisissez uniquement l'adresse de base de l'instance. Un "
        "sous-dossier simple est accepté, mais pas les requêtes, fragments, "
        "paramètres ni traversées de chemin."
    ),
    "error.target.port": "Cette adresse comporte un port invalide.",
    "error.target.no_host": "Cette adresse ne comporte aucun nom d'hôte.",
    "error.target.hostname_shape": (
        "Ce n'est pas un nom d'hôte que ce service peut analyser."
    ),
    "error.target.unresolved": "Ce nom d'hôte ne se résout pas.",
    "error.target.hostname_long": "Ce nom d'hôte est trop long.",
    "error.target.internal": (
        "Les adresses locales et internes ne peuvent pas être analysées."
    ),
    "error.target.private": (
        "Cette adresse pointe vers un réseau privé, de bouclage ou local, "
        "que ce service n'analysera pas."
    ),
    # ----------------------------------------------------------- result page
    "result.title": "Résultats de l'analyse",
    "result.description": (
        "Le résultat d'une analyse publique, lisible uniquement avec son "
        "propre identifiant."
    ),
    "result.kicker": "Rapport de terrain",
    "result.heading": "Résultat de l'analyse",
    "result.track.title": (
        "Le canal de version par rapport auquel cette analyse a été notée"
    ),
    "result.track.label": "Canal {track}",
    "result.another": "Analyser une autre instance",
    "result.progress.kicker": "En cours",
    "result.progress.queued.title": "En attente d'un travailleur de scan",
    "result.progress.queued.detail": (
        "Tous les travailleurs sont occupés pour le moment. Votre analyse "
        "garde sa place dans la file et démarre dès qu'un travailleur est "
        "libre."
    ),
    "result.progress.running.title": "Analyse de l'instance en cours",
    "result.progress.running.detail": (
        "Lecture de ce que l'instance publie : version, capacités, "
        "certificat, en-têtes et les points de terminaison qu'elle expose "
        "sans connexion."
    ),
    "result.progress.step.queued": "En file d'attente",
    "result.progress.step.running": "En cours",
    "result.progress.step.done": "Résultat",
    "result.progress.estimate": "La plupart des analyses se terminent en moins d'une minute.",
    "result.progress.elapsed": "{duration} écoulées",
    "result.progress.noscript": (
        "Cette page se met à jour elle-même grâce à JavaScript. Sans lui, "
        "rechargez la page dans quelques secondes pour voir le résultat."
    ),
    "result.progress.queue.position": (
        "Analyse en file d'attente. Position : #{position} sur {length}."
    ),
    "result.progress.queue.next": "Analyse en file d'attente. Vous êtes le prochain.",
    "result.progress.queue.waiting": (
        "En attente qu'un travailleur de scan la prenne en charge."
    ),
    "result.progress.done.title": "Rapport prêt",
    "result.progress.done.detail": "La note est disponible. Ouverture du rapport.",
    "result.progress.failed.title": "Analyse terminée",
    "result.progress.failed.detail": (
        "L'analyse n'a pas pu être menée à son terme. Ouverture de ce qui a "
        "été renvoyé."
    ),
    "result.failed.fallback": "L'analyse n'a pas pu être menée à son terme.",
    "result.failed.body": (
        "Rien n'a été noté, car rien d'exploitable n'a été renvoyé. Vérifiez "
        "que l'adresse est correcte, que l'instance est accessible depuis "
        "l'internet public, et qu'il s'agit bien d'une instance OpenCloud."
    ),
    "result.document.kicker": "Document de résultat",
    "result.document.heading": "Document de résultat",
    "result.document.lede": (
        "Le même document qu'évaluent le contrôle en ligne de commande et le "
        "plugin Nagios."
    ),
    "result.verdict.kicker": "Verdict",
    "result.verdict.heading": "Note globale",
    "result.verdict.dial": "Note {label}, {rating} sur 5",
    "result.facts.instance": "Instance",
    "result.facts.resolved": "Résolu vers",
    "result.facts.ipv6.heading": "Accessibilité IPv6",
    "result.facts.ipv6.note": (
        "Non vérifiée - ce déploiement n'a pas de connectivité IPv6 sortante, "
        "c'est donc simplement noté ici plutôt que compté contre l'instance."
    ),
    "result.facts.product": "Produit",
    "result.facts.track": "Canal de version",
    "result.facts.track.unknown": "inconnu",
    "result.facts.eol_tag": "Fin de vie",
    "result.facts.schedule": "Calendrier de versions",
    "result.facts.schedule.stale": (
        "{version} est plus récente que cette copie du calendrier des "
        "versions OpenCloud, ce calendrier est donc probablement obsolète. Ce "
        "n'est pas retenu contre l'instance -"
    ),
    "result.facts.schedule.stale_generated": (
        "{version} est plus récente que cette copie du calendrier des "
        "versions OpenCloud, générée le {generated}, ce calendrier est donc "
        "probablement obsolète. Ce n'est pas retenu contre l'instance -"
    ),
    "result.facts.schedule.link": "consultez la page de cycle de vie publiée",
    "result.facts.signin": "Connexion",
    "result.facts.signin.external": "Fournisseur externe",
    "result.facts.signin.upstream_tag": "amont",
    "result.facts.signin.version_unavailable": "version non exposée",
    "result.facts.signin.advisories": "consulter les avis de sécurité",
    "result.facts.signin.builtin": "Fournisseur d'identité intégré",
    "result.facts.signin.none": "Non détecté -",
    "result.facts.signin.link": "comment la connexion OpenCloud est configurée",
    "result.facts.proxy": "Proxy inverse",
    "result.facts.proxy.detected": "Détecté",
    "result.facts.office": "Bureautique",
    "result.facts.calendar": "Calendrier",
    "result.facts.calendar.detected": "Quelque chose répond sur le chemin CalDAV",
    "result.facts.newest": "Version la plus récente",
    "result.facts.score": "Score",
    "result.facts.score.value": "{rating} sur 5",
    "result.counter.critical": "Critique",
    "result.counter.warning": "Avertissement",
    "result.counter.info": "Info",
    "result.counter.advisories": "Avis de sécurité",
    "result.counter.passed": "Réussi",
    "result.verdict.why": "Pourquoi cette note :",
    "result.verdict.caveat": (
        "Une note indique que les contrôles ci-dessous ont réussi, pas que "
        "l'instance est sécurisée. Cette analyse n'est pas exhaustive : elle "
        "ne voit que ce que l'instance montre à un visiteur anonyme. "
        '<a href="#scan-limits">Ce qu\'elle ne peut pas voir</a>.'
    ),
    "result.fix": "Correctif :",
    "result.documentation": "Documentation",
    "result.explain.title": "Ce que signifie ce contrôle",
    "result.plan.kicker": "Plan de remédiation",
    "result.plan.heading": "Ce qui vous mène à {label}",
    "result.plan.then": "puis {label}",
    "result.plan.still": "toujours {label}",
    "result.plan.note": (
        "L'ordre est celui qui est rentable le plus tôt, et la note à côté "
        "d'une étape est celle qu'obtiendrait l'instance une fois cette "
        "étape et toutes celles qui la précèdent réalisées. Les constats de "
        "même gravité partagent un même plafond, si bien que la note ne "
        "bouge que lorsque le dernier d'entre eux a disparu - c'est pourquoi "
        "une étape peut être nécessaire tout en ne promettant rien à elle "
        "seule."
    ),
    "result.plan.blocked.heading": "Ce qui plombe la note, sans pouvoir être corrigé",
    "result.plan.blocked.note": (
        "OpenCloud fige ces éléments en dur, si bien qu'aucun paramètre n'y a "
        "d'effet. C'est la raison pour laquelle le plan ci-dessus s'arrête là "
        "où il s'arrête."
    ),
    "result.eol.alert": (
        "Cette version ne reçoit plus de correctifs de sécurité. Rien "
        "d'autre sur cette page ne peut faire remonter la note tant qu'elle "
        "n'est pas mise à niveau."
    ),
    "result.advisories.kicker": "Avis de sécurité",
    "result.advisories.heading": "Avis de sécurité connus pour cette version",
    "result.advisories.lede": "Avis publiés dont la plage concernée inclut {version}.",
    "result.advisories.fallback_id": "avis",
    "result.advisories.unrated": "non noté",
    "result.advisories.no_summary": "Aucun résumé publié.",
    "result.advisories.read": "Lire l'avis",
    "result.findings.kicker": "Constats",
    "result.findings.heading": "Contrôles en échec",
    "result.findings.lede": (
        "Chacun plafonne la note au niveau que sa gravité autorise. Corrigez "
        "d'abord les constats critiques : ce sont eux qui plombent le plus "
        "le score."
    ),
    "result.findings.filter.aria": "Filtrer les constats par gravité",
    "result.findings.filter.active": "Affichage des constats de gravité {severity} uniquement.",
    "result.findings.filter.clear": "Afficher tous les constats",
    "result.findings.allclear.tag": "Tout est en ordre",
    "result.findings.allclear.body": (
        "Tous les contrôles exécutés par ce scanner ont réussi sur cette "
        "instance."
    ),
    "result.hardening.kicker": "Durcissement",
    "result.hardening.heading": "Durcissement à ajouter",
    "result.hardening.lede": (
        "Des paramètres qui ne sont pas activés. Aucun d'entre eux n'est une "
        "vulnérabilité active ; chacun supprime une voie d'entrée."
    ),
    "result.hardening.tag": "durcissement",
    "result.header.tag": "en-tête",
    # ------------------------------------------------- configuration fragment
    "result.fragment.kicker": "La correction, écrite",
    "result.fragment.heading": "À coller dans votre configuration",
    "result.fragment.lede": (
        "Les constats ci-dessus, dans la syntaxe du fichier qui doit changer. "
        "Choisissez où votre instance est configurée."
    ),
    "result.fragment.caution": (
        "Lisez la ligne « Correction » de chaque constat avant de coller. Ce "
        "sont les valeurs que les vérifications recherchent, pas un examen de "
        "ce dont votre déploiement a besoin."
    ),
    "result.fragment.picker": "Format de configuration",
    "result.fragment.file": "À placer dans {name}.",
    "result.fragment.copy": "Copier",
    "result.fragment.copied": "Copié",
    "result.fragment.copy_failed": "Copie impossible",
    "result.fragment.nothing": (
        "Rien ici ne se règle de cette façon. Ce qui reste ouvert relève de "
        "{flavours}."
    ),
    "result.fragment.elsewhere": (
        "Ceux-ci se corrigent ailleurs - ils relèvent de {flavours} :"
    ),
    "result.fragment.undecided": (
        "Ceux-ci n'ont aucune valeur à coller : la bonne est une décision "
        "propre à ce déploiement, et la ligne « Correction » du constat est "
        "la réponse entière."
    ),
    # ------------------------------------------------------------ scan again
    "result.rescan": "Analyser à nouveau",
    "result.rescan.ready": "Cette instance peut être analysée à nouveau.",
    "result.rescan.wait": "Nouvelle analyse possible dans {countdown}.",
    "result.rescan.note": (
        "Même cible, mêmes exemptions, même canal de version - pour que le "
        "prochain résultat soit comparable à celui-ci. L'attente est ce qui "
        "maintient ce petit service debout ; le scanner est libre et tourne "
        "sur votre propre machine sans aucune limite :"
    ),
    "result.rescan.self_host": "l'exécuter vous-même",
    "result.excluded.kicker": "Exclu",
    "result.excluded.heading": "Signalé, mais non comptabilisé",
    "result.excluded.waived.heading": "Vous avez demandé à ignorer ceci",
    "result.excluded.waived.note": (
        "Ils ont tout de même échoué. Ils n'ont simplement pas plombé la "
        "note."
    ),
    "result.excluded.unfixable.heading": "Personne ne peut modifier ces éléments",
    "result.excluded.unfixable.note": (
        "OpenCloud fige ces indicateurs en dur, si bien qu'ils se lisent de "
        "la même façon sur toutes les instances existantes. Ils sont "
        "affichés par souci d'exhaustivité et exclus de la note."
    ),
    "result.scope.kicker": "Périmètre",
    "result.scope.heading": "Ce que cette analyse ne peut pas voir",
    "result.scope.body": (
        "Tout ce qui précède a été lu sans se connecter, ce qui est à la "
        "fois l'objectif et la limite. <strong>L'absence de constat n'est "
        "pas une preuve de sécurité</strong>, et la meilleure note que cette "
        "page puisse donner n'affirme pas que l'instance est sécurisée - "
        "seulement que rien de ce qui a été contrôlé ici n'a posé problème. "
        "Des catégories entières échappent totalement à une analyse non "
        "authentifiée : le système d'exploitation et ses paquets, "
        "l'environnement d'exécution des conteneurs, la configuration propre "
        "du proxy inverse, les sauvegardes et leurs restaurations, le "
        "stockage derrière l'instance, la gestion des secrets et des clés, "
        "les comptes, les mots de passe et la connexion multifacteur, les "
        "permissions sur les partages existants, la chaîne "
        "d'approvisionnement logicielle, et tout ce qui ne se révèle qu'à un "
        "utilisateur connecté. C'est aussi le cas de ces deux éléments, qui "
        "semblent pourtant devoir être visibles et ne le sont pas :"
    ),
    "result.scope.audit": (
        "<strong>Journalisation d'audit.</strong> Le service d'audit "
        "d'OpenCloud ne fait que consommer le bus d'événements interne - il "
        "ne publie aucun point de terminaison et n'apparaît dans aucun "
        "document non authentifié - si bien que son fonctionnement ne peut "
        "absolument pas être établi depuis l'extérieur. Ce n'est pas "
        "contrôlé."
    ),
    "result.scope.integrations": (
        "<strong>Si une intégration bureautique ou de calendrier est "
        "configurée <em>correctement</em>.</strong> Cette page ne signale "
        "que le fait qu'un fournisseur d'application est enregistré, ou que "
        "quelque chose répond sur le chemin CalDAV. Les règles de partage, "
        "les secrets WOPI et la configuration propre du second service se "
        "trouvent tous derrière une connexion et ne sont pas contrôlés."
    ),
    "result.tls.kicker": "Transport",
    "result.tls.heading": "Sécurité du transport",
    "result.tls.lede": (
        "Ce que la couche TLS a indiqué avant qu'un seul octet HTTP ne soit "
        "échangé. Les constats ci-dessus en tiennent déjà compte ; ceci en "
        "est la mesure sous-jacente."
    ),
    "result.tls.protocol": "Protocole",
    "result.tls.bits": "({bits} bit)",
    "result.tls.deprecated": "Versions obsolètes",
    "result.tls.deprecated.accepted": "Encore acceptées : {list}",
    "result.tls.deprecated.refused": "Refusées : {list}",
    "result.tls.chain": "Chaîne",
    "result.tls.chain.trusted": "Fiable",
    "result.tls.chain.not_established": "Non établie",
    "result.tls.chain.not_trusted": "Non fiable",
    "result.tls.chain.incomplete_note": "- aucun chemin vers une racine publique",
    "result.tls.issued_to": "Délivré à",
    "result.tls.unnamed": "sans nom",
    "result.tls.issued_by": "Délivré par",
    "result.tls.unknown": "inconnu",
    "result.tls.valid_for": "Valide pour",
    "result.tls.validity": "Validité",
    "result.tls.validity.range": "{start} à {end}",
    "result.tls.validity.expired": "- expiré il y a {days} jour(s)",
    "result.tls.validity.remaining": "- {days} jour(s) restant(s)",
    "result.tls.lifetime": "Délivré pour",
    "result.tls.lifetime.days": "{days} jour(s)",
    "result.tls.ocsp": "Agrafage OCSP",
    "result.tls.ocsp.stapled": "Une réponse de révocation est agrafée",
    "result.tls.ocsp.not_stapled": "Non agrafé",
    "result.tls.ocsp.undetermined": "Non déterminé",
    "result.raw.kicker": "Données brutes",
    "result.raw.heading": "Détails techniques",
    "result.raw.lede": (
        "Le document de résultat complet, exactement tel que le plugin le "
        "voit."
    ),
    "result.raw.summary": "Afficher le JSON brut",
    "result.export.kicker": "Export",
    "result.export.heading": "Emportez ce résultat avec vous",
    "result.export.lede": (
        "La même analyse, présentée de quatre façons. Chacune est générée à "
        "la demande et disparaît avec l'analyse elle-même."
    ),
    "result.export.pdf": "Rapport PDF",
    "result.export.pdf.hint": "Pour un ticket, une revue ou une impression.",
    "result.export.csv": "CSV",
    "result.export.csv.hint": "Une ligne par constat, pour un tableur.",
    "result.export.sarif": "SARIF",
    "result.export.sarif.hint": "Pour un tableau de bord d'analyse de code.",
    "result.export.json": "JSON",
    "result.export.json.hint": "Le document brut qu'évalue le plugin.",
    "result.export.passed.heading": "Ce qui est déjà en règle",
    "result.export.passed.note": (
        "Ces contrôles sont revenus propres, ils n'apparaissent donc pas dans le "
        "plan ci-dessus."
    ),
    "result.share.kicker": "Partager",
    "result.share.heading": "Partager ce rapport",
    "result.share.lede": (
        "Par courriel, ou via votre propre presse-papiers. Rien ne transite "
        "par ce service et aucune autre entreprise n'est sollicitée."
    ),
    "result.share.warning": (
        "L'adresse de cette page est la seule chose qui la protège : qui la "
        "détient peut lire le rapport jusqu'à son expiration. La publier dans "
        "un canal la partage avec tout le monde, et avec tout ce qui consulte "
        "les liens pour en faire un aperçu. Copiez plutôt le résumé lorsque "
        "ce sont les constats qui comptent."
    ),
    "result.share.email": "Partager par courriel",
    "result.share.email.hint": (
        "Ouvre votre propre logiciel de messagerie avec le message prêt. Rien "
        "ne quitte votre navigateur avant l'envoi."
    ),
    "result.share.email.subject": "Rapport de sécurité OpenCloud pour {target}",
    "result.share.email.body": (
        "Voici le rapport de sécurité de notre instance OpenCloud :\n\n"
        "{url}\n\n"
        "Ce lien est ce qui donne accès au rapport : traitez-le comme un mot "
        "de passe. Il expire de lui-même, après quoi la page n'existe plus."
    ),
    "result.share.link": "Copier le lien",
    "result.share.link.hint": (
        "L'adresse de cette page. Quiconque la reçoit peut ouvrir le rapport."
    ),
    "result.share.summary": "Copier le résumé",
    "result.share.summary.hint": (
        "Les constats en texte, sans aucun lien. Le plus sûr à coller dans un "
        "canal de discussion."
    ),
    "result.share.summary.body": (
        "Rapport de sécurité OpenCloud - {domain}\n"
        "Note {label} ({rating} sur 5)\n"
        "Critiques {critical} | Avertissements {warning} | Info {info} | "
        "Alertes {advisories} | Réussis {passed}\n"
        "Mesuré avec check-opencloud-security."
    ),
    "result.share.done": "Copié",
    "result.share.failed": "Copie impossible",
    "result.share.fallback": "L'adresse de ce rapport :",
    "result.feedback.prompt": "Vous pensez que l'analyse s'est trompée ?",
    "result.feedback.link": "Signaler un faux positif ou un faux négatif",
    "result.expiry.one": (
        "Cette page expire dans environ 1 minute, après quoi le lien cesse "
        "de fonctionner et le résultat disparaît."
    ),
    "result.expiry.many": (
        "Cette page expire dans environ {minutes} minutes, après quoi le "
        "lien cesse de fonctionner et le résultat disparaît."
    ),
    # ----------------------------------------- transport facts beside the grade
    "tls.fact.protocol": "Version TLS",
    "tls.fact.protocol.detail": "accepte aussi {list}",
    "tls.fact.expiry": "Expiration du certificat",
    "tls.fact.expiry.expired": "expiré il y a {days} jour(s)",
    "tls.fact.expiry.remaining": "{days} jour(s) restant(s)",
    "tls.fact.chain": "Chaîne",
    "tls.fact.chain.incomplete": "Incomplète",
    "tls.fact.chain.incomplete.detail": "aucun chemin vers une racine publique",
    "tls.fact.chain.untrusted": "Non fiable",
    "tls.fact.chain.untrusted.detail": "autosigné, ou autorité inconnue",
    "tls.fact.chain.unknown": "Non établie",
    "tls.fact.chain.unknown.detail": "la négociation n'a jamais atteint le certificat",
    "tls.fact.chain.ok": "Complète et fiable",
}
