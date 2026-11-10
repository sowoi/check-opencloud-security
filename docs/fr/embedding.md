# Intégrer OpenCloud dans une iframe : ce que ce scanner vérifie, et pourquoi

Une application peut intégrer le client web OpenCloud dans une `iframe`, par
exemple comme sélecteur de fichiers ou panneau d'aperçu. La page parente et le
client intégré échangent des messages via `postMessage` ; l'authentification
déléguée permet en outre à la page parente de fournir une session. Le scanner
lit le fichier public `/config.json` pour vérifier quelles origines le client
intégré considère comme fiables.

Si `/config.json` ne peut pas être lu, ou s'il ne publie aucun bloc `embed`,
les deux contrôles réussissent : l'intégration n'est pas configurée,
il n'y a donc aucune restriction d'origine susceptible d'échouer.

<!-- TOC -->
* [Intégrer OpenCloud dans une iframe : ce que ce scanner vérifie, et pourquoi](#embedding-opencloud-in-an-iframe-what-this-scanner-checks-and-why)
  * [1. L'intégration accepte-t-elle les messages de n'importe quelle origine : `webEmbedMessageOriginRestricted`](#1-does-the-embed-accept-messages-from-any-origin-webembedmessageoriginrestricted)
  * [2. L'authentification déléguée accepte-t-elle une origine non validée : `webEmbedDelegatedAuthenticationRestricted`](#2-does-delegated-authentication-accept-an-unvalidated-origin-webembeddelegatedauthenticationrestricted)
  * [Gravité et effet sur la note](#severity-and-rating-impact)
<!-- TOC -->


## 1. L'intégration accepte-t-elle les messages de n'importe quelle origine : `webEmbedMessageOriginRestricted` {#1-does-the-embed-accept-messages-from-any-origin-webembedmessageoriginrestricted}

Le scanner lit `options.embed.messagesOrigin` dans la configuration web
publique. `WEB_OPTION_EMBED_MESSAGES_ORIGIN=*` signifie que le client intégré
échangera du trafic `postMessage` avec **n'importe quelle** page qui l'encadre,
et non seulement avec l'intégration pour laquelle il a été configuré. N'importe
quel site sur Internet peut alors charger le client web d'OpenCloud dans un
cadre masqué ou déguisé et commencer à lui envoyer des messages que le client
traitera comme provenant d'un parent de confiance.

**Correction :** définissez `WEB_OPTION_EMBED_MESSAGES_ORIGIN` sur l'origine
exacte de la page autorisée à intégrer le client (schéma, hôte et port - pas un
joker ni un chemin), ou désactivez complètement l'intégration si rien ne
l'utilise réellement.

## 2. L'authentification déléguée accepte-t-elle une origine non validée : `webEmbedDelegatedAuthenticationRestricted` {#2-does-delegated-authentication-accept-an-unvalidated-origin-webembeddelegatedauthenticationrestricted}

L'authentification déléguée permet à la page parente de transmettre sa propre
session au cadre intégré, afin que le visiteur n'ait pas à se connecter deux
fois. Ce contrôle échoue uniquement lorsque les **deux** conditions sont
réunies : `delegateAuthentication` vaut `true` *et* `delegateAuthenticationOrigin`
est vide - autrement dit, le client accepte une session déléguée d'un cadre
parent sans vérifier qui est réellement ce parent. Quiconque peut encadrer la
page peut lui transmettre une session, ce qui fait de ce contrôle le plus grave
des deux : il s'agit d'un contournement d'authentification, et non d'un simple
excès de portée dans l'échange de messages, d'où sa gravité `critical` face au
`high` précédent.

**Correction :** définissez
`WEB_OPTION_EMBED_DELEGATE_AUTHENTICATION_ORIGIN` sur l'origine parente de
confiance exacte, ou désactivez purement et simplement l'authentification
déléguée si l'intégration n'en a pas besoin. L'authentification déléguée avec
une origine définie n'est pas en soi un constat - seule la combinaison
« activée et sans restriction » l'est.

## Gravité et effet sur la note {#severity-and-rating-impact}

Les deux sont des `extraChecks`, signalés et plafonnant la note dès que
`/config.json` publie un bloc `embed` - `webEmbedMessageOriginRestricted` en
`high` (plafonne la note à `C`), `webEmbedDelegatedAuthenticationRestricted` en
`critical` (la plafonne à `D`) - voir le tableau des contrôles supplémentaires
dans [le README principal](scanner-checks.md#what-the-scanner-checks). Aucun des
deux ne nécessite `--check-hardening`.
