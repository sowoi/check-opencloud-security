# Déploiement sécurisé

Une analyse externe ne couvre qu’une partie de l’exploitation sécurisée d’OpenCloud. Ce
guide couvre le reste du travail : politiques du fournisseur d’identité, journalisation
d’audit, règles de pare-feu, maintenance de l’hôte, sauvegardes et consignes aux
utilisateurs.

Appliquez ces mesures en complément des analyses planifiées. La dernière section explique
ce que des analyses régulières peuvent détecter une fois le déploiement en place.

> Chaque paramètre ci-dessous est tiré de la documentation d’OpenCloud et y
> renvoie. OpenCloud évolue vite ; lorsqu’une variable citée ici contredit la
> page liée, c’est la page liée qui a raison, et
> [un ticket](https://github.com/sowoi/check-opencloud-security/issues) est le
> bienvenu.

<!-- TOC -->
* [Exploiter OpenCloud dans une infrastructure sécurisée](#running-opencloud-in-a-secure-infrastructure)
  * [L’architecture d’un déploiement défendable](#the-shape-of-a-defensible-deployment)
  * [1. Placer un vrai fournisseur d’identité devant OpenCloud](#1-put-a-real-identity-provider-in-front)
    * [Le pourquoi avant le comment](#why-before-how)
    * [Ce dont OpenCloud a besoin, quel que soit le fournisseur](#what-opencloud-needs-whichever-provider-you-pick)
    * [Keycloak](#keycloak)
    * [Authentik](#authentik)
    * [Authelia](#authelia)
    * [L’authentification Basic, la faille de l’ensemble](#basic-authentication-is-the-hole-in-all-of-this)
  * [2. Activer le journal d’audit, puis le lire](#2-turn-the-audit-log-on-then-read-it)
    * [Le service d’audit ne s’exécute pas par défaut](#the-audit-service-does-not-run-by-default)
    * [Sortir le journal de la machine](#getting-the-log-off-the-box)
    * [Sur quoi alerter réellement](#what-to-actually-alert-on)
    * [Conservation et obligations légales](#retention-and-the-law)
  * [3. Configurer correctement le pare-feu](#3-firewall-it-properly)
    * [Les ports, et ceux qui ont leur place sur Internet](#the-ports-and-which-of-them-belong-on-the-internet)
    * [Un pare-feu d’hôte compatible avec Docker](#a-host-firewall-that-works-with-docker)
    * [Le trafic sortant compte aussi](#egress-matters-too)
  * [4. À la base de tout : l’hôte et les données](#4-underneath-it-all-the-host-and-the-data)
  * [5. Ce que les utilisateurs doivent savoir](#5-what-the-people-using-it-should-know)
    * [Pour toute personne disposant d’un compte](#for-everybody-with-an-account)
    * [Pour les administrateurs](#for-administrators)
  * [6. La place de ce scanner : la supervision continue](#6-where-this-scanner-fits-continuous-monitoring)
    * [Ce qu’une analyse planifiée détecte et qu’un audit ponctuel manque](#what-a-scheduled-scan-catches-that-a-one-off-audit-does-not)
    * [Une supervision qui en vaut la peine](#a-monitoring-setup-that-is-worth-having)
    * [Ce qu’il ne vous dira volontairement pas](#what-it-deliberately-will-not-tell-you)
  * [Liste de contrôle](#checklist)
  * [Pour aller plus loin](#where-to-go-next)
  * [Marques et affiliation](#trademarks-and-affiliation)
<!-- TOC -->


## L’architecture d’un déploiement défendable {#the-shape-of-a-defensible-deployment}

```
                    internet
                        │
                   443/tcp only
                        │
              ┌─────────▼─────────┐
              │   reverse proxy   │  TLS, HSTS, security headers,
              │  (nginx/Caddy/…)  │  rate limits, TRACE refused
              └─────────┬─────────┘
                        │  private network, no published ports
         ┌──────────────┼──────────────┐
         │              │              │
  ┌──────▼─────┐ ┌──────▼─────┐ ┌──────▼──────┐
  │ OpenCloud  │ │  identity  │ │    audit    │
  │   :9200    │ │  provider  │ │   service   │
  └──────┬─────┘ └────────────┘ └──────┬──────┘
         │                             │
   ┌─────▼──────┐               ┌──────▼──────┐
   │  storage   │               │  log sink   │  off-host, append-only
   └────────────┘               └─────────────┘
```

N’exposez que les points d’entrée publics prévus, appliquez votre politique de
connexion au niveau du fournisseur d’identité et envoyez les enregistrements
d’audit vers un système distinct. Les sections suivantes décrivent chaque
élément.

## 1. Placer un vrai fournisseur d’identité devant OpenCloud {#1-put-a-real-identity-provider-in-front}

### Le pourquoi avant le comment {#why-before-how}

OpenCloud inclut un fournisseur d’identité (`idp`) et une gestion des identités
(`idm`) pour qu’une première installation fonctionne. Un fournisseur externe
est utile lorsqu’une organisation a besoin d’un cycle de vie des comptes
partagé, d’une authentification multifacteur et de politiques cohérentes entre
les services :

- **Seconds facteurs.** Un fournisseur externe vous offre TOTP, WebAuthn ou
  les passkeys pour toutes vos applications, configurés une seule fois.
- **Cycle de vie.** Quelqu’un part et vous désactivez un seul compte, et non un
  compte par service.
- **Politique de session.** Verrouillage après des tentatives échouées, durée
  de session, confiance dans les appareils, accès conditionnel : tout cela
  relève du fournisseur.
- **Audit.** Les tentatives de connexion sont enregistrées là où les connexions
  sont traitées, c’est-à-dire là où un enquêteur les cherchera.

Ce scanner indique sous `identityProvider` quel fournisseur il a trouvé, et
abaisse le constat sur l’authentification HTTP Basic de medium à low lorsqu’il
détecte un fournisseur externe - voir
[Authentification](authentication.md#6-can-the-identity-provider-be-found-at-all-identityproviderdetected).

> **Étape par étape, pour chacun des trois :** cette section donne le résumé et
> le raisonnement. [Placer un fournisseur d’identité devant OpenCloud, étape par
> étape](identity-providers.md) est le tutoriel : installation de chaque
> fournisseur, les quatre clients OpenCloud dont chacun a besoin, vérification
> du résultat et migration d’une instance qui a déjà des comptes.

### Ce dont OpenCloud a besoin, quel que soit le fournisseur {#what-opencloud-needs-whichever-provider-you-pick}

Les variables sont les mêmes pour les trois ; seuls l’URL de l’émetteur et la
façon de créer le client diffèrent. D’après
[le guide des IdP externes d’OpenCloud](https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp) :

| Variable | Effet |
|:---------|:-------------|
| `OC_OIDC_ISSUER` | L’URL de l’émetteur du fournisseur, par exemple `https://id.example.com/realms/opencloud` |
| `OC_EXCLUDE_RUN_SERVICES` | Ajoutez `idp` pour que le fournisseur intégré ne démarre pas |
| `PROXY_OIDC_ACCESS_TOKEN_VERIFY_METHOD` | `jwt`, pour que les jetons soient vérifiés à l’aide des clés publiées par le fournisseur plutôt qu’en l’interrogeant à chaque requête |
| `PROXY_OIDC_REWRITE_WELLKNOWN` | `true`, pour que les clients qui découvrent `/.well-known/openid-configuration` sur l’hôte OpenCloud soient dirigés vers le vrai fournisseur |
| `PROXY_USER_OIDC_CLAIM` | Le claim qui identifie un utilisateur, généralement `preferred_username` |
| `PROXY_USER_CS3_CLAIM` | L’attribut OpenCloud auquel il est comparé, généralement `username` |
| `PROXY_AUTOPROVISION_ACCOUNTS` | `true` crée un compte lors de la première connexion |
| `PROXY_ROLE_ASSIGNMENT_DRIVER` | `oidc` pour prendre les rôles dans un claim, `default` pour donner le même rôle à tout le monde |
| `PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM` | Le claim qui porte les rôles ; `roles` par défaut |
| `GRAPH_ASSIGN_DEFAULT_USER_ROLE` | `false` lorsque les rôles viennent du fournisseur, sinon chaque utilisateur reçoit discrètement aussi le rôle par défaut |

Examinez ensemble le provisionnement des comptes et l’attribution des rôles :

**Le provisionnement automatique est une décision de contrôle d’accès.** Avec
`PROXY_AUTOPROVISION_ACCOUNTS=true`, toute personne que votre fournisseur
authentifie obtient un compte OpenCloud lors de sa première visite. C’est
correct lorsque l’application OpenCloud du fournisseur est limitée à un groupe,
et incorrect lorsque le fournisseur authentifie toute votre organisation :
limitez l’accès côté fournisseur, et non en désactivant le provisionnement
automatique pour créer les comptes à la main.

**L’attribution des rôles depuis un claim exige de désactiver le rôle par
défaut.** Définir `PROXY_ROLE_ASSIGNMENT_DRIVER=oidc` en laissant
`GRAPH_ASSIGN_DEFAULT_USER_ROLE=true` est l’erreur de configuration qui donne à
tout le monde un rôle que vous n’aviez pas prévu.

### Keycloak {#keycloak}

> [Le tutoriel Keycloak étape par étape](identity-providers.md#tutorial-a-keycloak)
> couvre tout le travail ; voici les grandes lignes.

Le choix le plus courant lorsqu’une organisation en exploite déjà un. Créez un
realm (ou réutilisez le vôtre), puis un client :

- **Client type** OpenID Connect. Enregistrez séparément les clients web,
  bureau, Android et iOS, avec les ID client indiqués dans le tutoriel lié.
- **Client public** avec PKCE : les clients d’OpenCloud sont des clients publics
  et ne peuvent pas garder de secret. Réglez *Proof Key for Code Exchange* sur
  `S256`.
- Les **Valid redirect URIs** doivent inclure l’adresse de bouclage du client de
  bureau (`http://127.0.0.1:*` et `http://localhost:*`) ainsi que votre adresse
  web.
- **Émetteur** : `https://id.example.com/realms/opencloud`.

Pour les rôles, ajoutez un mapper *User Client Role* qui place les rôles du
client dans un claim `roles`, puis définissez
`PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM=roles`. Donnez au realm une politique de mot
de passe et exigez au minimum l’OTP pour le rôle administrateur.

### Authentik {#authentik}

> [Le tutoriel Authentik étape par étape](identity-providers.md#tutorial-b-authentik)
> couvre tout le travail ; voici les grandes lignes.

Ce dépôt fournit déjà une pile Authentik, mais dans un autre but : elle protège
[le point de terminaison MCP du service d’analyse](authentik.md), pas OpenCloud.
La configuration du fournisseur a la même forme :

- Créez un **OAuth2/OpenID Provider**, avec le flux d’autorisation
  `implicit consent` pour une application interne de confiance.
- **Client type** public, avec PKCE obligatoire.
- Définissez les URI de redirection comme ci-dessus, avec une expression
  régulière pour la plage de bouclage.
- L’émetteur est `https://id.example.com/application/o/<application-slug>/`.
  La barre oblique finale compte.
- Associez l’application à un groupe pour que tous les utilisateurs Authentik
  n’obtiennent pas un compte OpenCloud, puis activez
  `PROXY_AUTOPROVISION_ACCOUNTS`.

[`authentik/blueprints/`](../../authentik/blueprints/) dans ce dépôt est un
exemple complet de provisionnement d’un fournisseur à partir d’un fichier plutôt
qu’en cliquant, utile à reprendre quel que soit ce que vous configurez.

### Authelia {#authelia}

> [Le tutoriel Authelia étape par étape](identity-providers.md#tutorial-c-authelia)
> couvre tout le travail ; voici les grandes lignes.

Le plus léger des trois, et bien adapté lorsque le reverse proxy assure déjà
l’authentification déléguée (forward auth). Le fournisseur OpenID Connect
d’Authelia se configure dans `configuration.yml` plutôt que dans une interface :

- Enregistrez un client sous `identity_providers.oidc.clients` avec
  `public: true`, `require_pkce: true` et `pkce_challenge_method: S256`.
- Portées `openid`, `profile`, `email`, `groups`.
- L’émetteur est `https://auth.example.com`.
- Faites correspondre les groupes aux rôles OpenCloud avec
  `PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM=groups`.

Les règles de contrôle d’accès d’Authelia sont l’endroit naturel pour exiger
deux facteurs spécifiquement pour OpenCloud :

```yaml
access_control:
  rules:
    - domain: opencloud.example.com
      policy: two_factor
```

### L’authentification Basic, la faille de l’ensemble {#basic-authentication-is-the-hole-in-all-of-this}

Rien de ce qui précède ne s’applique à un client qui ne sait pas utiliser
OpenID Connect : agendas CalDAV et CardDAV, montages WebDAV, tâches de
sauvegarde. Ces clients s’authentifient en HTTP Basic, et
`PROXY_ENABLE_BASIC_AUTH=true` rouvre un chemin qui contourne votre fournisseur
et tous ses seconds facteurs.

Laissez-la à `false` si rien n’en a besoin. Si quelque chose en a besoin, la
solution est **des jetons d’application, pas les mots de passe des comptes** :
ce qui peut être rejoué est alors révocable et n’est jamais l’identifiant que
protège votre fournisseur d’identité. Ce scanner signale `basicAuthDisabled`
en medium, ou en low lorsqu’il voit un fournisseur externe, parce
que ce compromis est parfois voulu - voir
[Authentification](authentication.md).

## 2. Activer le journal d’audit, puis le lire {#2-turn-the-audit-log-on-then-read-it}

### Le service d’audit ne s’exécute pas par défaut {#the-audit-service-does-not-run-by-default}

OpenCloud dispose d’un
[service d’audit](https://docs.opencloud.eu/docs/dev/server/services/audit/),
mais il ne fait pas partie des services démarrés par défaut. Rien n’enregistre
qui a partagé quoi tant que vous ne l’avez pas démarré :

```bash
# Add it to the services that run, alongside the default set.
OC_ADD_RUN_SERVICES=audit
```

Il enregistre trois catégories utiles :

- **Opérations sur le système de fichiers** : création, suppression,
  déplacement, y compris la corbeille et les versions.
- **Gestion des utilisateurs** : comptes créés et supprimés.
- **Partage** : partages avec des utilisateurs et des groupes, liens publics,
  modifications de droits et appels à l’API de partage depuis les clients.

La troisième catégorie est la plus importante ici. Ce scanner peut vous dire que
des liens publics peuvent être créés sans mot de passe
([`publicLinkPasswordEnforced`](sharing.md)) ; seul le journal d’audit peut vous
dire que quelqu’un en a créé 4 000 mardi dernier.

Configurez-le avec les variables de
[la référence du service d’audit](https://docs.opencloud.eu/docs/dev/server/services/audit/environment-variables) :

| Variable | Valeur par défaut | Valeur à définir |
|:---------|:--------|:------------------|
| `AUDIT_LOG_TO_CONSOLE` | `true` | À laisser activé lorsqu’un pilote de journalisation de conteneur envoie stdout ailleurs |
| `AUDIT_LOG_TO_FILE` | `false` | `true` si vous préférez écrire un fichier |
| `AUDIT_FILEPATH` | *(vide)* | Obligatoire pour la journalisation dans un fichier |
| `AUDIT_FORMAT` | `json` | Conservez `json` ; le format minimal est fait pour une lecture humaine, pas pour un collecteur |
| `AUDIT_LOG_LEVEL` | `error` | Augmentez-le, sinon vous n’enregistrerez presque rien |
| `OC_EVENTS_ENDPOINT` | `127.0.0.1:9233` | Le broker d’événements que lit le service |
| `AUDIT_EVENTS_AUTH_USERNAME` / `_PASSWORD` | *(vide)* | Définissez les deux dès que le broker n’est plus sur l’interface de bouclage |
| `AUDIT_EVENTS_ENABLE_TLS` | `false` | `true` lorsque le broker est joint par le réseau |

La valeur par défaut `error` d’`AUDIT_LOG_LEVEL` est le détail qui piège : démarrer
le service sans toucher au niveau produit un journal techniquement actif et
pratiquement vide.

### Sortir le journal de la machine {#getting-the-log-off-the-box}

Un journal d’audit conservé uniquement sur la machine auditée est une preuve
qu’un attaquant peut modifier. Expédiez-le ailleurs :

```yaml
# docker-compose fragment: hand stdout to the host's journal, which a
# collector then forwards off the machine.
services:
  opencloud:
    logging:
      driver: journald
      options:
        tag: opencloud
```

Quel que soit le collecteur - Loki, Elasticsearch, un serveur syslog, un service
géré -, les propriétés à exiger sont les mêmes : **ajout seul du point de vue de
l’émetteur, dans un domaine de confiance différent de l’instance, avec sa
propre durée de conservation.** Un collecteur dans lequel les identifiants
d’OpenCloud permettent de supprimer des données ne vaut guère mieux qu’un
fichier local.

### Sur quoi alerter réellement {#what-to-actually-alert-on}

Alerter sur tout revient à n’alerter sur rien. Une courte liste qui a fait ses
preuves :

- Un **lien public créé sans mot de passe ou sans expiration**, en particulier
  sur un espace qui n’est habituellement pas partagé.
- **Des droits de partage élargis** sur quoi que ce soit, surtout au profit d’un
  groupe.
- **Un compte créé ou doté d’un rôle d’administration** en dehors de votre
  processus de provisionnement habituel.
- **Un téléchargement ou une suppression en masse** : un volume d’opérations sur
  les fichiers depuis un compte, nettement supérieur à sa propre référence.
- **Des anomalies de connexion**, qui viennent de votre fournisseur d’identité
  et non d’OpenCloud : déplacement impossible, pic d’échecs, première connexion
  depuis un nouveau pays.

### Conservation et obligations légales {#retention-and-the-law}

Le journal d’audit d’un service de fichiers indique qui a consulté quels
documents, ce qui, dans la plupart des juridictions, constitue des données
personnelles soumises à une durée de conservation limitée plutôt qu’à une
conservation illimitée. Fixez cette durée, consignez-la et faites-la
appliquer par le collecteur. Si vous êtes soumis au RGPD, ce journal entre dans
votre registre des activités de traitement.

## 3. Configurer correctement le pare-feu {#3-firewall-it-properly}

### Les ports, et ceux qui ont leur place sur Internet {#the-ports-and-which-of-them-belong-on-the-internet}

| Port | Ce que c’est | Exposé sur Internet ? |
|:-----|:-----------|:-------------------------|
| 443 | Le reverse proxy | **Oui** - celui-ci, et lui seul |
| 80 | HTTP simple | Uniquement pour rediriger vers 443, ou pas du tout |
| 9200 | Le service proxy propre à OpenCloud | **Non.** Le publier permet aux clients de contourner entièrement votre politique TLS et d’en-têtes |
| 9233 | Le broker d’événements (NATS) | **Non** |
| 9205, 9141, 9124, 9134, 9239 | Écouteurs de débogage par service : métriques, affichage de la configuration, éventuellement pprof | **Non.** Ils sont liés à `127.0.0.1` par défaut ; en atteindre un depuis l’extérieur signifie qu’un mappage de port de conteneur l’a publié |
| 22 | SSH | Réseau d’administration ou VPN uniquement, jamais l’Internet ouvert |

Ce scanner vérifie depuis l’extérieur les trois dernières lignes -
`backendPortClosed`, `debugPort:*` et `debugEndpoint:*`, décrits dans
[Chemins exposés et points de terminaison de débogage](exposure.md). Il vérifie
votre pare-feu à votre place, depuis le seul point de vue qui compte.

### Un pare-feu d’hôte compatible avec Docker {#a-host-firewall-that-works-with-docker}

L’erreur courante : **Docker écrit ses propres
règles iptables, et elles sont évaluées avant celles d’UFW.** Un conteneur
démarré avec `-p 9200:9200` est accessible depuis Internet, quoi qu’indique
`ufw status`. Deux solutions, et il vous en faut une :

**Ne publier que sur l’interface de bouclage.** La solution la plus simple, qui
ne nécessite aucun pare-feu :

```yaml
services:
  opencloud:
    ports:
      # Not "9200:9200" - that binds 0.0.0.0.
      - "127.0.0.1:9200:9200"
```

Mieux encore, ne publiez rien et laissez le reverse proxy joindre OpenCloud par
son nom de service sur un réseau Docker. Un port qui n’est pas publié ne peut
pas être mal configuré.

**Ou faire respecter le pare-feu de l’hôte par Docker.** Dans
`/etc/docker/daemon.json` :

```json
{
  "iptables": true,
  "ip-forward": true
}
```

puis filtrez dans `DOCKER-USER`, la seule chaîne que Docker vous laisse :

```bash
# Everything reaching a container from outside must come via the proxy.
iptables -I DOCKER-USER -i eth0 -p tcp --dport 9200 -j DROP
```

L’équivalent [nftables](https://nftables.org/), si c’est votre génération :

```
table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iif lo accept
    tcp dport { 80, 443 } accept
    tcp dport 22 ip saddr 10.0.0.0/8 accept
  }
}
```

Quelle que soit la méthode, vérifiez depuis une autre machine plutôt que de vous
fier à la configuration : `nmap -Pn -p 9200,9205,9233 opencloud.example.com`
depuis l’extérieur de l’hôte, ou simplement ce scanner, qui sonde exactement ces
ports :

```bash
check-opencloud-security --host opencloud.example.com --check-hardening --debug
```

### Le trafic sortant compte aussi {#egress-matters-too}

Les règles entrantes sont celles que l’on écrit. Les règles sortantes sont
celles qui limitent ce qu’une compromission permet de faire : exfiltration,
shell inversé, enrôlement dans un botnet. Un hôte OpenCloud a besoin de
remarquablement peu : DNS, NTP, l’annuaire ACME s’il émet ses propres
certificats, votre miroir de paquets, et les backends de stockage ou de
messagerie que vous avez délibérément configurés. Refusez le reste par défaut.

## 4. À la base de tout : l’hôte et les données {#4-underneath-it-all-the-host-and-the-data}

Brièvement, car rien de ceci n’est propre à OpenCloud et tout est essentiel :

- **Des mises à jour de sécurité automatiques** sur l’hôte, et un vrai
  processus de mise à jour pour la version d’OpenCloud elle-même. Ce scanner
  note la version que vous utilisez ([cycle de vie](lifecycle.md)) ; il ne peut
  rien installer.
- **Un chiffrement complet du disque** sur le support du stockage, pour qu’un
  disque mis au rebut ou volé ne soit pas une fuite de données.
- **Des sauvegardes que vous avez déjà restaurées.** Une sauvegarde jamais
  testée peut se révéler inutilisable. Conservez une copie hors ligne ou sur un
  stockage à écriture unique : un rançongiciel cherche d’abord la sauvegarde.
- **Le moindre privilège pour le compte de service.** Les unités systemd de
  [`contrib/systemd/`](../../contrib/systemd/) montrent le principe :
  `DynamicUser=yes`, `ProtectSystem=strict`, `NoNewPrivileges=yes`, un
  `CapabilityBoundingSet=` vide. Lancez `systemd-analyze security <unit>` sur
  les vôtres.
- **Séparez le reverse proxy d’OpenCloud**, sur des hôtes différents ou au moins
  dans des conteneurs différents, pour qu’une compromission du proxy ne soit pas
  immédiatement une compromission du stockage.

## 5. Ce que les utilisateurs doivent savoir {#5-what-the-people-using-it-should-know}

La plupart des incidents réels sur un service de fichiers ne sont pas des
exploits. Quelqu’un partage le mauvais dossier par un lien public, ou réutilise
un mot de passe qui figurait dans une fuite de données. C’est un problème de
documentation et de valeurs par défaut, pas de correctifs.

### Pour toute personne disposant d’un compte {#for-everybody-with-an-account}

- **Un lien public est un mot de passe.** Quiconque possède l’URL a accès aux
  données - transférée, collée dans un ticket ou conservée dans une archive de
  messagerie. Protégez-le par un mot de passe et définissez une expiration.
- **Vérifiez ce que vous partagez avant de le partager.** Partager un dossier
  parent partage tout ce qu’il contient, y compris ce qui y sera ajouté plus
  tard.
- **Enregistrez un second facteur**, de préférence une passkey ou une clé
  matérielle plutôt que TOTP.
- **Les mots de passe d’application sont destinés aux applications.** Votre
  client d’agenda reçoit son propre jeton révocable ; il ne reçoit jamais le mot
  de passe de votre compte.
- **Supprimer un partage n’annule pas l’envoi d’un fichier.** Partez du principe
  que tout ce qui a été partagé a été téléchargé.
- **Signalez immédiatement un partage erroné.** Le délai pendant lequel un
  administrateur peut révoquer un lien et consulter le journal d’audit est
  court, et personne n’est sanctionné pour l’avoir signalé rapidement.

### Pour les administrateurs {#for-administrators}

- **Réexaminez régulièrement les partages.** Les liens publics s’accumulent ;
  presque aucun n’est jamais supprimé délibérément.
- **Disposez d’une procédure de départ** qui couvre le fournisseur d’identité,
  les jetons d’application et les partages créés par la personne.
- **Connaissez le fonctionnement normal de votre instance.** La liste d’alertes
  ci-dessus ne fonctionne que par rapport à une référence.
- **Notez qui appeler.** Un incident à 3 h du matin n’est pas le moment de
  découvrir que personne ne sait qui est responsable du stockage.

## 6. La place de ce scanner : la supervision continue {#6-where-this-scanner-fits-continuous-monitoring}

### Ce qu’une analyse planifiée détecte et qu’un audit ponctuel manque {#what-a-scheduled-scan-catches-that-a-one-off-audit-does-not}

Un audit de sécurité est une photographie. Une infrastructure est un film. Tout
ce qui figure sur cette page peut être vrai le lundi et faux le jeudi, et les
causes sont banales plutôt que spectaculaires :

- Un **certificat expire**, ou est renouvelé par un certificat qui ne couvre pas
  tous les noms.
- Un **reverse proxy est reconfiguré** pour un service sans rapport et cesse
  d’envoyer `Strict-Transport-Security`, ou commence à répondre à `TRACE`.
- Quelqu’un **publie un port de débogage** en cherchant un problème de
  performance et oublie de le retirer.
- Une **version arrive en fin de vie**, ce qui est un changement dans le monde
  plutôt que dans votre déploiement : l’instance entièrement prise en charge le
  mois dernier ne reçoit plus de correctifs de sécurité, et rien sur votre hôte
  n’a changé pour vous en avertir.
- Un **avis de sécurité est publié** pour la version que vous utilisez.
- Un **nouveau déploiement** est mis en place à partir d’un fichier compose
  copié qui publie encore le port 9200.

Exécuter ce plugin de façon planifiée transforme chacun de ces événements en
alerte le jour même, depuis l’extérieur de l’instance, c’est-à-dire du même
point de vue qu’un attaquant. C’est l’argument en faveur de la supervision
continue, en une phrase : **les incidents se logent dans l’intervalle entre la
panne d’un déploiement et le moment où quelqu’un la remarque, et seule une
vérification régulière, à quelques minutes d’intervalle, raccourcit cet
intervalle.**

### Une supervision qui en vaut la peine {#a-monitoring-setup-that-is-worth-having}

Commencez ici, puis lisez [Planification](scheduling.md) ou
[Icinga2 / Nagios](installation.md#icinga2-nagios) selon votre plateforme :

```bash
check-opencloud-security \
  --host opencloud.example.com \
  --check-hardening \
  --baseline /var/lib/check-opencloud-security/baseline.json \
  --warn-on-new \
  --webhook-url https://hooks.example.com/opencloud \
  --webhook-on warning
```

Quatre choix, chacun justifié :

- **`--check-hardening`** inclut les en-têtes et les mesures de durcissement, et
  pas seulement la note.
- **`--baseline` avec `--warn-on-new`** alerte sur ce qui a *changé* plutôt que
  sur l’état accepté. Une instance avec un constat que vous avez consciemment
  décidé d’accepter reste silencieuse jusqu’à l’apparition d’un second - voir
  [Ne signaler que ce qui a changé](../../README.md#reporting-only-what-changed).
- **Un webhook**, pour que l’alerte atteigne une personne plutôt qu’un tableau
  de bord que personne n’ouvre.
- **Les constats que vous acceptez sont exemptés explicitement**, avec
  `--ignore-hardening`, ce qui les conserve dans le document de résultat et dans
  le rapport tout en les retirant de l’alerte. Une exemption est une décision
  qui porte un nom, pas un contrôle réduit au silence - voir
  [Accepter un constat que vous ne corrigerez pas](hardening.md#accepting-a-finding-you-are-not-going-to-fix).

Pour un parc, [Analyser plusieurs instances](many-instances.md) décrit un
fichier de configuration par instance et la façon de garder les exemptions sous
contrôle sur l’ensemble. Pour les graphiques et les tendances à long terme,
consultez [Prometheus et Grafana](prometheus.md) : la note sous forme de série
temporelle est un résumé étonnamment efficace à présenter aux personnes qui ne
lisent pas les alertes.

### Ce qu’il ne vous dira volontairement pas {#what-it-deliberately-will-not-tell-you}

Être clair sur ce point est ce qui rend le reste du rapport digne de confiance :

- **Rien de ce qui se trouve derrière une connexion.** L’analyse ne
  s’authentifie jamais : elle voit ce que voit un visiteur anonyme, et rien de
  plus. Votre modèle de droits, l’organisation de vos espaces et le contenu de
  vos partages lui sont invisibles.
- **Rien sur la configuration de votre fournisseur d’identité.** Elle détecte sa
  présence et nomme l’éditeur ; l’exigence d’un second facteur se règle entre
  vous et le fournisseur.
- **Rien sur votre journal d’audit.** Que le service tourne, que quelqu’un le
  lise et qu’il quitte l’hôte échappe à ce qu’une analyse HTTP peut observer.
- **Rien sur les règles de votre pare-feu**, seulement sur leur effet sur la
  poignée de ports qu’elle sonde.
- **Aucune exploitation.** Elle n’essaie jamais de charge utile, ne devine
  jamais de mot de passe, et la seule sonde d’identifiants qu’elle effectue
  n’utilise que les mots de passe de démonstration publiés par OpenCloud dans sa
  propre documentation.

[Ce à quoi l’analyse ne répond volontairement
pas](scanner-checks.md#what-the-scan-deliberately-does-not-answer) donne la
version complète de cette liste.

## Liste de contrôle {#checklist}

Imprimez-la, discutez-la, rayez ce qui ne s’applique pas :

- [ ] Seul le port 443 (et le 80, pour la redirection) est accessible depuis Internet
- [ ] Le port 9200 et tous les ports de débogage `92xx` sont inaccessibles depuis
      l’extérieur - vérifié depuis un autre hôte, pas d’après la configuration
- [ ] Le trafic sortant est limité à ce dont l’instance a réellement besoin
- [ ] Un fournisseur d’identité externe gère la connexion
- [ ] Un second facteur est exigé, au minimum pour les administrateurs
- [ ] `PROXY_ENABLE_BASIC_AUTH=false`, ou des jetons d’application délivrés aux
      clients qui en ont besoin
- [ ] `GRAPH_ASSIGN_DEFAULT_USER_ROLE=false` si les rôles viennent d’un claim
- [ ] Le provisionnement automatique est limité par un groupe côté fournisseur
- [ ] `OC_ADD_RUN_SERVICES=audit` et `AUDIT_LOG_LEVEL` relevé au-dessus de `error`
- [ ] Le journal d’audit est expédié hors de l’hôte, avec une durée de conservation délibérée
- [ ] Des alertes sont définies pour les liens publics, l’élargissement des partages et les changements de rôle
- [ ] TLS par une autorité de certification publique, renouvelé automatiquement, avec un enregistrement CAA
- [ ] Les en-têtes de sécurité sont définis au niveau du proxy - voir [reverse proxies](reverse-proxy.md)
- [ ] `OC_CORS_ALLOW_ORIGINS` est restreint par rapport à sa valeur par défaut `*`
- [ ] Les liens publics exigent un mot de passe et une expiration
- [ ] Des sauvegardes existent, quittent l’hôte et ont déjà été restaurées
- [ ] L’hôte est corrigé automatiquement ; la version d’OpenCloud est dans sa période de support
- [ ] Cette vérification s’exécute de façon planifiée, avec une référence, et alerte une personne

## Pour aller plus loin {#where-to-go-next}

| Page | Pourquoi |
|:-----|:----|
| [Reverse proxies](reverse-proxy.md) | La configuration nginx, Apache, Caddy, Traefik et HAProxy derrière l’essentiel de la section 3 |
| [TLS et certificats](tls.md) | Tous les contrôles de transport, et ce qu’est un bon certificat |
| [Chemins exposés et points de terminaison de débogage](exposure.md) | Ce par rapport à quoi la section pare-feu est vérifiée |
| [Authentification](authentication.md) | Les constats sur le fournisseur d’identité et l’authentification Basic, en détail |
| [Partage par lien public](sharing.md) | La politique de partage dans laquelle travaillent vos utilisateurs |
| [Planification](scheduling.md) | Timers systemd et cron pour la supervision de la section 6 |
| [Analyser plusieurs instances](many-instances.md) | Dès qu’il y en a plus d’une |
| [Prometheus et Grafana](prometheus.md) | La note sous forme de série temporelle |
| [Qu’est-ce qu’OpenCloud](what-is-opencloud.md) | Le contexte, si vous venez d’ownCloud ou de Nextcloud |

## Marques et affiliation {#trademarks-and-affiliation}

Ce projet est un projet communautaire indépendant. Il n’est **pas** affilié à
OpenCloud GmbH, ni approuvé, parrainé ou soutenu par elle, et rien sur cette
page ne constitue une déclaration officielle concernant les logiciels
OpenCloud.

« OpenCloud », le logo OpenCloud ainsi que tous les noms et marques associés
appartiennent à leurs propriétaires respectifs. Ils ne figurent ici que pour
identifier le logiciel que vérifie cet outil. Tous les droits sur OpenCloud
restent la propriété d’OpenCloud GmbH.
