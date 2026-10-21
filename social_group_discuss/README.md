# Groupes — conversation Discuss

Chaque groupe (`social_group`) a sa conversation de groupe Discuss, comme les relations de `social_relation` :

- elle est créée avec les premiers membres du groupe, au nom du groupe ;
- elle garde les mêmes membres : qui rejoint le groupe entre dans la conversation, qui le quitte en sort ;
- renommer le groupe la renomme ; supprimer le groupe en retire tous les membres (l'historique reste aux administrateurs) ;
- la page du groupe offre « Conversation du groupe » à ses membres ;
- l'application mobile la liste avec les autres conversations (`social_mobile_chat`, `kind: "group"`).

À l'installation, les groupes existants reçoivent leur conversation.
