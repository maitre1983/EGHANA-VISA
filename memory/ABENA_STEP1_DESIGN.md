# ABENA — Étape 1 : conception technique (centraliser les informations et connecter ABENA au backend de façon sécurisée)
Statut : CONCEPTION UNIQUEMENT. Aucun code n'est écrit avant votre validation.

## 0. Constats techniques supplémentaires (relevés pendant la conception)
- Les moyens de paiement sont transmis à ABENA comme tous **désactivés**. ama_chat.py lit le champ `enabled`, alors que la configuration utilise `active`. ABENA peut donc dire à tort que la crypto n'est pas acceptée.
- Le champ `duration` lu par ABENA n'existe pas : la durée de validité réelle se trouve dans `days`. Le délai propre à chaque visa (`processing_time_label`) n'est pas lu.
- Les délais Priority/Express sont écrits en dur à 6 endroits : ama_chat.py, Apply.jsx, Prices.jsx, Home.jsx, FAQ.jsx et server.py (e-mails, lignes 796 et 1893).
- Les 4 documents envoyés par le visiteur (face_photo, passport_copy, passport_cover, flight_ticket) sont fixés dans Apply.jsx et vérifiés par le serveur (server.py, ligne 655). La liste annoncée par ABENA (5 éléments) ne correspond pas à ce que le formulaire exige.

## 1. Paramètres à centraliser
| Groupe | Où | Modifiable par l'admin | Changement |
|---|---|---|---|
| Catégories de visa, prix, actif oui/non, durée de validité (days), Priority/Express disponibles | settings.visa_types (existant) | Oui (écrans existants) | **Aucun**. Prix et règles financières intacts ; ABENA ne reçoit que les visas actifs. |
| Suppléments Priority/Express, remise USDT | settings (existant) | Oui (existant) | **Aucun**. Simple lecture. |
| Moyens de paiement actifs | settings.payment_methods (existant) | Oui (existant) | Lecture corrigée (`active`). |
| Délais affichés Regular/Priority/Express (FR + EN) | **nouveau** settings.processing_tiers | Oui | Valeurs initiales = textes actuels, donc aucun changement visible. |
| Délai propre à chaque visa (FR) | visa_types[].processing_time_label_fr (nouveau champ) | Oui | Valeur initiale = traduction du texte actuel. |
| Documents requis : libellés FR/EN, aide, visas concernés | **nouveau** settings.document_requirements | Libellés et aide oui ; les 4 identifiants restent fixes | Protège l'envoi des fichiers. |
| Informations réglementaires et politiques (CEDEAO, fièvre jaune, dépassement de séjour, remboursement, remise du visa) | **nouvelle** collection abena_knowledge | Oui, avec validation | Voir § 4. |
| Moteur ABENA (legacy / v2) | settings.abena.engine | Oui | Bouton de retour arrière immédiat. |

## 2. Endpoints
**Réutilisés sans modification** : tous les /api/admin/settings/* des prix, suppléments, visas et paiements, ainsi que les paiements et dossiers.
**Étendu (ajout seulement)** : GET /api/config reçoit `processing_tiers` et `document_requirements` (champs publics uniquement).
**Nouveaux (admin, protégés par require_admin et enregistrés dans le journal d'activité existant)** :
- GET/PUT /api/admin/abena/processing-tiers : libellés uniquement, aucun montant.
- GET/PUT /api/admin/abena/documents : libellés et aide ; identifiants non modifiables.
- GET/POST/PUT /api/admin/abena/knowledge, POST /{id}/approve, POST /{id}/archive.
- GET /api/admin/abena/context-preview : montre exactement ce qu'ABENA voit.
- POST /api/admin/abena/engine : bascule entre l'ancien et le nouveau moteur.
Aucun endpoint public ne donne accès à la base de connaissances brute ni aux données des dossiers.

## 3. Connexion sécurisée d'ABENA
- Nouveau service `backend/abena_facts.py` : il construit un instantané de faits sur une liste blanche de champs. Chaque fait porte un identifiant et sa source (ex. `visa.tourist_evisa.price`, `kb.ecowas#v3`). Il exclut les visas et moyens de paiement inactifs, les secrets et les clés API. Il ne contient aucune donnée client.
- ama_chat.py ne contient plus aucune valeur métier. Il reçoit uniquement cet instantané.
- ABENA n'accède jamais à MongoDB ; seul le service lit la configuration. Pas d'outil d'écriture, pas d'accès aux paiements.
- Choix : injecter l'instantané plutôt que laisser l'IA appeler des outils à l'étape 1. Les données sont peu nombreuses ; c'est plus fiable, moins coûteux et entièrement contrôlable. Les outils seront réservés à l'étape 3 (statut d'un dossier après vérification d'identité).

## 4. Informations réglementaires (abena_knowledge)
Chaque fiche contient : `{id, category: regulatory|policy|procedure, title, answer_fr, answer_en, source_name, source_url, validated_by, validated_at, review_due_at, status: draft|approved|archived, version}`.
- ABENA n'utilise que les fiches **approuvées et non expirées** (date de révision non dépassée).
- Une fiche réglementaire ne peut pas être approuvée sans source officielle (URL) ni date de validation.
- Toute modification crée une nouvelle version et repasse la fiche en brouillon.
- Les 5 textes actuellement écrits en dur sont importés en **brouillon**. Tant qu'ils ne sont pas validés, ABENA répond qu'elle ne peut pas confirmer et propose un conseiller (choix de votre part, voir § 9).

## 5. Contrôle des réponses
1. **Prompt v2** : citer uniquement les faits fournis ; sinon dire que l'information n'est pas disponible et proposer un conseiller. Présentation : société privée indépendante qui transmet les dossiers aux autorités ghanéennes compétentes, seules décisionnaires. Jamais de garantie d'approbation. Le mot « official » est supprimé.
2. **Contrôleur après réponse** (`backend/abena_guard.py`, sans IA, déterministe) :
   - Il repère dans la réponse chaque montant (« $ », USD, dollars), pourcentage et délai (jours / days / heures / hours / h).
   - Il les compare à la liste autorisée : prix, suppléments, prix + supplément, remise, délais configurés, taille maximale des fichiers, durée de validité.
   - Il rejette les expressions interdites : « approbation garantie », « guaranteed », « service officiel », « government agency », etc.
   - En cas d'écart, la réponse est remplacée par un message sûr en FR/EN et un conseiller est proposé. La raison est enregistrée dans chat_log (`guard: {passed, reasons}`).
3. Statistique admin : taux de réponses bloquées, pour améliorer la base de connaissances.

## 6. Fichiers et collections concernés
- Backend : `abena_facts.py` (nouveau), `abena_guard.py` (nouveau), `ama_chat.py`, `server.py` (endpoints, /api/config, libellés des e-mails), `seed_data.py` (valeurs par défaut identiques aux textes actuels).
- Frontend : `Apply.jsx`, `Prices.jsx`, `Home.jsx`, `FAQ.jsx` (délais lus dans la configuration, textes actuels en secours) ; nouvelle page `AdminAbena.jsx` + menu dans AdminLayout.
- Collections : `settings` (ajout de clés uniquement), `abena_knowledge` (nouvelle), `chat_log` (ajout du champ guard).
- **Non touchés** : applications, payments, crypto_payments, hubtel_callbacks, transactions, prix, suppléments, webhooks.

## 7. Protections contre les régressions
- Migration au démarrage **additive et idempotente** : elle n'ajoute une clé que si elle est absente et n'écrase jamais visa_types ni les montants. Avant/après, /api/config doit renvoyer exactement les mêmes prix et suppléments (test automatique).
- Interrupteur `abena.engine` : « legacy » garde l'ABENA actuelle, « v2 » active le nouveau moteur. Il sera livré en production sur « legacy », puis basculé après votre validation.
- Les pages publiques gardent les textes actuels en secours si la configuration est vide.
- Tests de non-régression existants rejoués (paiements, Hubtel, conformité, admin).

## 8. Plan de tests et retour arrière
**Tests**
1. Tests unitaires du contrôleur : environ 30 cas FR/EN (montant inventé, délai inventé, garantie, mot « officiel », réponses correctes acceptées).
2. Tests unitaires du service de faits : visa inactif exclu, aucun secret présent, fiche brouillon ou expirée exclue.
3. Tests des endpoints admin : 401 sans connexion, approbation refusée sans source, versions, journal d'activité.
4. Test de bout en bout : changer un libellé de délai dans l'admin, puis vérifier Apply, Prices, Home, l'e-mail et ABENA.
5. Questions de référence (20 FR + 20 EN) : tarifs, délais, documents, paiement, visa inexistant, « garantissez-vous l'approbation ? », plusieurs questions dans un même message, statut de dossier (doit renvoyer vers une vérification ou un conseiller).
6. Agent de test complet sur le frontend et le backend, en préproduction uniquement.

**Retour arrière**
- Immédiat : interrupteur sur « legacy » depuis l'admin, sans redéploiement.
- Code : point de restauration Emergent (rollback) en préproduction, ou redéploiement de la version précédente en production.
- Données : les ajouts n'ont aucun effet sur l'ancien code, qui ignore les nouvelles clés. Aucune suppression ni modification de données existantes.

## 9. Décisions attendues
1. Informations réglementaires actuelles : (a) importées en brouillon, ABENA ne les cite plus jusqu'à votre validation (recommandé) ; ou (b) approuvées provisoirement avec une date de révision proche.
2. Valider que les 4 documents envoyés restent fixes (seuls les libellés et l'aide sont modifiables).
3. Valider la correction de la lecture des moyens de paiement (`active`), qui ne change rien aux paiements eux-mêmes.
