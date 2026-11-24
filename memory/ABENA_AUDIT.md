# Audit ABENA (Livrable B) — juin 2026

## 1. Architecture actuelle
- Fichiers : backend/ama_chat.py (prompt + appel au modèle), server.py POST /api/chat (tickets, journal), frontend AbenaChat.jsx.
- Modèle : Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via la clé Emergent, modifiable par le réglage admin `ai_model`.
- La conversation est SANS MÉMOIRE : un nouvel objet est créé à chaque message, et seul le dernier message est envoyé au modèle. ABENA ne se souvient donc pas de ce qui a été dit juste avant.
- ABENA n'a aucun outil : pas d'accès aux dossiers, à MongoDB, aux secrets ni aux paiements (bon point de sécurité). Elle reçoit seulement un bloc de texte construit à partir des réglages admin.

## 2. Origine des informations
| Information | Source | Fiable ? |
|---|---|---|
| Catégories et prix des visas | Réglages admin (visa_types) | Oui. Mais les visas désactivés sont aussi envoyés, et le champ « duration » n'existe pas (il vaut vide). |
| Suppléments Priority/Express | Réglages admin. Valeurs par défaut écrites dans le code (25 / 50) si le réglage manque | Partiellement |
| **Délais de traitement** | **ÉCRITS EN DUR dans ama_chat.py, lignes 79-81** (« 5–7 business days », « 3 business days », « 48–72 hours ») | **Non vérifiables** |
| Documents requis | Liste écrite en dur (5 éléments), sans lien avec le formulaire | Non |
| Pays CEDEAO exemptés, politique de dépassement de séjour, remboursement, fièvre jaune, mode de remise du visa | Écrits en dur | Non validés |
| Moyens de paiement | Réglages admin (actifs et inactifs mélangés) | Partiellement |
| Statut d'un dossier | Aucun accès (le champ tracking_no existe dans l'API mais n'est jamais envoyé) | — |

**Pourquoi ABENA annonce des délais :** ils viennent du code, pas de la configuration. On retrouve les mêmes valeurs fixes dans Apply.jsx (« 3 business days », « 48–72h ») et dans les e-mails (server.py, lignes 796 et 1893). Seul le délai Regular de chaque visa (processing_time_label) est un vrai réglage, et ABENA ne le lit pas.

## 3. Tickets
- Un ticket est créé à CHAQUE message transmis à un conseiller, donc des doublons dans une même conversation.
- L'e-mail du visiteur est demandé APRÈS la création du ticket. Il n'est envoyé qu'avec le message suivant : un visiteur qui laisse son e-mail puis part n'est jamais rattaché à son ticket.
- L'alerte admin réutilise le modèle « nouvelle demande de visa », avec des champs fictifs.
- La réponse de l'admin est toujours envoyée en anglais. Aucun suivi d'envoi (envoyé, échec, pas de moyen de contact).
- Statuts limités à open / resolved. Le ticket ne contient que le dernier message, pas un résumé du contexte.

## 4. Risques de réponses inventées
- Les règles de fiabilité reposent uniquement sur le prompt, sans aucun contrôle des chiffres après la réponse.
- Le seuil « moins de 70 % de confiance » est jugé par le modèle lui-même : ce n'est pas mesurable.
- Le prompt dit « official 24/7 AI Customer Success Agent ». Le mot « official » est à retirer pour la conformité.
- Le prompt ne contient aucune règle interdisant de promettre une approbation. Il ne précise pas non plus que les autorités ghanéennes sont seules décisionnaires.

## 5. Données personnelles et sécurité
- chat_log conserve tous les messages sans durée limite, y compris les numéros de passeport que les visiteurs peuvent taper.
- /api/chat n'a ni limite de fréquence ni limite de longueur côté serveur : risque d'abus et de coût.
- Pas d'accès aux dossiers, donc aucune fuite possible aujourd'hui. Mais il n'existe pas non plus de vérification d'identité pour un futur accès.

## 6. Architecture cible et plan (à valider avant tout développement)
1. **Source unique de vérité** : délais Priority/Express (FR/EN) et documents requis par type de visa réglables dans l'admin. Apply, les e-mails et ABENA lisent les mêmes valeurs, et seuls les visas actifs sont proposés. Aucun prix existant n'est modifié.
2. **Moteur à outils en lecture seule** : catalogue des visas, options de traitement, moyens de paiement actifs, recherche dans la base de connaissances validée. Un contrôle après réponse vérifie que chaque prix ou délai cité figure dans les données ; sinon, transmission à un humain.
3. **Statut d'un dossier** : numéro de suivi + e-mail du dossier (ou 4 derniers caractères du passeport). Seuls le statut et l'étape sont renvoyés, avec une limite de tentatives.
4. **Mémoire de conversation** : les 10 derniers échanges de la session sont relus. Les questions multiples sont traitées point par point.
5. **Tickets** : un seul ticket par conversation, résumé du contexte, coordonnées ajoutées au ticket existant (e-mail facultatif), modèle d'alerte dédié, réponse dans la langue du visiteur, statuts fiables (open / pending / answered / closed + statut d'envoi).
6. **Base de connaissances supervisée** : un bouton « Proposer à la base » sur une réponse admin crée un brouillon, qu'un admin valide. Chaque fiche garde sa source et son auteur. Aucun apprentissage automatique.
7. **Conformité et sécurité** : nouveau prompt (prestataire privé indépendant, transmission aux autorités ghanéennes, aucune promesse d'approbation, mot « official » retiré), limite de fréquence et de longueur, masquage des numéros de passeport et e-mails dans les journaux, conservation 90 jours.
8. **Qualité** : jeu de questions-réponses de référence FR/EN rejoué à chaque modification, et tableau de bord des statistiques ABENA.

## Hubtel — adresse IP de sortie
- IP de sortie observée en production : **130.211.210.175** (Google Cloud NAT, cluster target-2). Elle a été relevée depuis le même cluster, pas directement sur le serveur en production.
- Rien ne garantit qu'elle reste fixe après un redéploiement : demander confirmation écrite au support Emergent (déploiement 2c861289-b5f5-4b46-a752-993f9f7157b3).
- Alternative robuste : un proxy de sortie à IP fixe. Il est déjà prévu dans Admin → Hubtel (`outbound_proxy_url`) ; on fait alors autoriser l'IP du proxy par Hubtel.
- Aucune erreur 403 ni « status check failed » vue sur les 24 dernières heures (au-delà, les journaux ne sont pas consultables).
- L'IP de l'aperçu (35.193.209.116) ne sert pas en production.
