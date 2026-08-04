# À faire — MicroDigests

Ce qui reste sur ce projet. Ouvre ce fichier en début de session, coche, et
dis-moi ce qui a bougé.

Dernière mise à jour : 4 août 2026.

---

## Ce qui est fini

La structure est faite et validée. On n'y revient pas :

- La page d'accueil, deux versions de mascotte (cute et grumpy)
- Le design de la page écrit une seule fois, partagé par les deux versions
- Chaque mascotte dans son propre fichier
- `python3 site/verify_pages.py` vérifie que tout tient, en français clair
- `site/index.html` renvoie vers la version choisie
- Le marquage des médias d'État, élargi

---

## Retouches — toi

Petits changements de texte et de design. À remplir quand tu les repères :

- [ ] …
- [ ] …
- [ ] …

Comment procéder : ouvre les deux pages, note ce qui te gêne, dis-le-moi en
vrac. Le texte vit dans les `.html`, le look dans `page.css`. Une retouche de
texte ne peut pas casser le design, et l'inverse non plus.

---

## Décisions qui t'appartiennent

- [ ] **Quelle mascotte est la publique ?** Aujourd'hui c'est la cute
      (`framed.html`). Pour passer à la grumpy, c'est une adresse à changer
      dans `site/index.html`, rien d'autre.
- [ ] **Basculer sur `main` ?** Tout le travail est sur la branche
      `landing-page-and-mascots`. Tant que ce n'est pas sur `main`, c'est rangé
      de côté. Le bot, lui, tourne depuis `main` et n'est pas concerné.

---

## Mettre le site en ligne

Le site n'existe que sur ton disque. Pour qu'il vive sur internet :

- [ ] **Activer GitHub Pages.** Le dépôt est déjà public, donc c'est gratuit.
      Le site est dans `site/`, et Pages ne sait servir que la racine ou un
      dossier `docs/`. Deux solutions : renommer le dossier, ou ajouter un
      workflow qui publie `site/`. Je recommande le workflow, ça évite de
      renommer ce que tu connais déjà.
      Adresse obtenue, sans rien payer : `ilo930.github.io/MicroDigests_bot`
- [ ] **Acheter un nom de domaine** (optionnel, ~10 à 15 € par an). Tu le
      déclares dans les réglages Pages, tu fais pointer le domaine vers GitHub,
      et le site répond dessus. Le domaine t'appartient : si tu changes
      d'hébergeur un jour, il te suit.

Une chose à savoir avant de publier : le dépôt étant public, le code du bot est
déjà visible de tous. Les clés, elles, ne le sont pas — elles vivent dans les
secrets GitHub et dans `.env`, qui n'est pas suivi. Publier le site ne change
rien à ça.

---

## Ensuite

Une fois cette liste vide, ce projet est clos et on passe à autre chose.
