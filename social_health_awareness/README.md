# Coin Santé — réduction des risques

Guide public de réduction des risques. Il parle de pratiques et de risques, jamais de personnes ni de statuts. Aucune donnée de santé individuelle n'est collectée.

## Fonctionnement

- `/sante` (alias `/reduction-des-risques`) affiche, pour chaque pratique active, les infections concernées avec un niveau de risque (faible, modéré, élevé), les mesures de prévention propres à la pratique, les mesures transversales et les ressources locales. La page est publique, sans connexion.
- `/sante/auto-evaluation` permet de cocher des pratiques et d'obtenir un résumé : infections, niveau de risque, prévention, dépistage. Le calcul se fait dans le navigateur; les cases cochées ne sont pas envoyées au serveur.
- `/sante/affiche` produit une affiche imprimable avec un code QR vers `/sante`, généré par le service de codes-barres d'Odoo.
- Une carte « Coin Santé » apparaît sur le portail `/my`. Des liens sont ajoutés à la page Sécurité de `social_safety` et à la liste des négociations de `social_negotiation`.
- Un compteur agrégé compte les visites de `/sante` et de l'auto-évaluation, par page et par jour. Il n'enregistre ni IP, ni session, ni utilisateur.

## Configuration

Les modérateurs gèrent le contenu dans le menu **Coin Santé** : Pratiques, Infections, Risques (matrice), Préventions, Ressources locales et Consultations. Une ressource locale est liée à une fiche contact (`res.partner`) qui porte le nom, l'adresse et le téléphone.

Les données fournies (matrice et ressources) sont `noupdate` : une mise à jour n'écrase pas les modifications. Ce contenu est un exemple à faire valider par un professionnel de la santé avant toute mise en ligne réelle.

## Accès et limites

- Seul le groupe modérateur (`social_base.group_social_moderator`) a accès aux modèles; les consultations sont en lecture seule.
- Les pages publiques lisent le contenu en `sudo` et n'affichent que les ressources actives.
- Archiver une ressource n'archive pas sa fiche contact.

## Dépendances et tests

Dépend de `website`, `social_base`, `social_safety` et `social_negotiation`. Le module n'a pas de tests unitaires. Le parcours E2E `tests/e2e/test_28_coin_sante.py` couvre les trois pages publiques :

```sh
make test-e2e
```
