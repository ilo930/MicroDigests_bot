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

## Format Instagram

- [ ] **Une version verticale du site pour Instagram.** Une capture vidéo du
      scroll, remise en page en vertical (1080 × 1920). À faire une fois les
      retouches finies, sinon la vidéo sera à refaire.
      À décider au moment venu : durée, si le texte reste lisible une fois
      recadré, et si on filme la grumpy ou les deux.

---

## Décisions qui t'appartiennent

- [x] **Quelle mascotte est la publique ?** La **grumpy**, décidé le 4 août.
      `site/index.html` renvoie vers `framed-mascot02.html`. La cute reste
      entière dans le projet, tu dois encore la retoucher.
- [ ] **Basculer sur `main` ?** Tout le travail est sur la branche
      `landing-page-and-mascots`. Tant que ce n'est pas sur `main`, c'est rangé
      de côté. Le bot, lui, tourne depuis `main` et n'est pas concerné.

---

## Mettre le site en ligne

Le site n'existe que sur ton disque. **Rien de la page n'est encore sur GitHub**
— le dépôt ne contient que le bot. Vérifié le 4 août.

Dans l'ordre :

- [x] **Le workflow de publication est écrit** : `.github/workflows/pages.yml`.
      Il publie `site/` à chaque fois qu'une modification arrive sur `main`, et
      il refuse de publier si `verify_pages.py` échoue. Une page cassée ne peut
      donc pas partir en ligne : c'est l'ancienne qui reste affichée.
- [ ] **Envoyer le travail sur GitHub** (`git push`). Rien n'est en ligne tant
      que ce n'est pas fait.
- [ ] **Activer Pages dans les réglages du dépôt**, source « GitHub Actions ».
      Un seul réglage à changer, une fois pour toutes.
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
