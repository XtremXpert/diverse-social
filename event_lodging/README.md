# Événement — Hébergement

Ce module associe un type d'hébergement aux billets d'événement : sans hébergement, lit simple ou lit double pour un couple. Il s'appuie sur `website_event_sale`.

## Fonctionnement

- Sur chaque billet (onglet Billets de l'événement), le champ **Type d'hébergement** vaut « Sans hébergement » par défaut.
- L'inscription reprend le type du billet. Pour un billet « Lit double (couple) », le champ **Partenaire 2 (couple)** est obligatoire et doit différer du participant principal.
- Sur le site, le formulaire d'inscription affiche une section « Informations du/de la partenaire » pour les billets en lit double : nom obligatoire, courriel facultatif.
- À la validation, le partenaire 2 est cherché par courriel (sans tenir compte de la casse). S'il n'existe pas, un contact est créé. Un contact existant garde son nom, même si le nom saisi diffère. Si plusieurs contacts partagent le courriel, le premier est utilisé et un avertissement est journalisé.
- Le formulaire de l'événement montre un bouton **Chambres** quand au moins une inscription non annulée a un hébergement. Il ouvre la liste « Chambres réservées », groupée par type d'hébergement.
- Les listes d'inscriptions affichent le type d'hébergement et le partenaire 2 en colonnes optionnelles.

## Accès et limites

- Les compteurs comptent une inscription par chambre ; un lit double compte pour une chambre.
- Le module ne gère ni le nombre de chambres disponibles ni leur attribution. La limite de places vient du billet lui-même.
- Le fichier `static/src/js/event_lodging.js` est vide : tout l'affichage est rendu côté serveur.

## Dépendances et tests

Dépend de `website_event_sale`. Les tests couvrent le type par défaut, les contraintes sur le partenaire 2 et le traitement du formulaire web.

```sh
odoo-dev test event_lodging test_db
```
